from collections.abc import Awaitable, Callable
from enum import Enum
from typing import Annotated, Any
from urllib.parse import urljoin

import xarray as xr
from fastapi import APIRouter, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from starlette.responses import Response
from xpublish import Dependencies, Plugin, hookimpl
from xpublish import hookspec as hookspec

from xpublish_ogc_core.models import (
    Collections,
    ConfClasses,
    LandingPage,
    Link,
    OGCException,
)

# Reusable `responses=` mapping documenting the OGC exception body that
# OGCExceptionRoute returns for errors, so OpenAPI matches the real responses.
OGC_EXCEPTION_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"model": OGCException, "description": "Not found"},
    422: {"model": OGCException, "description": "Invalid request"},
}

OGC_API_COMMON_CONFORMANCE_CLASSES = [
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/core",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/landing-page",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/json",
    "http://www.opengis.net/spec/ogcapi-common-1/1.0/conf/oas30",
    "http://www.opengis.net/spec/ogcapi-common-2/1.0/conf/collections",
]

OGC_REL_CONFORMANCE = "http://www.opengis.net/def/rel/ogc/1.0/conformance"
OGC_REL_DATA = "http://www.opengis.net/def/rel/ogc/1.0/data"


def _base_url(request: Request) -> str:
    """Return the externally visible API root for direct, proxied, and mounted apps."""
    base_url = str(request.base_url).rstrip("/")
    root_path = request.scope.get("root_path", "")
    app_root_path = request.scope.get("app_root_path", "")
    mount_path = root_path.removeprefix(app_root_path).rstrip("/")
    return f"{base_url}{mount_path}/"


class OgcPluginSpec(Plugin):
    """A specification for OGC plugins."""

    @hookspec
    def ogc_router(  # type: ignore[empty-body]
        self, deps: Dependencies
    ) -> Annotated[APIRouter, "An OGC specific router"]:
        """A hook specification for adding OGC specific routers."""
        pass

    @hookspec
    def ogc_conformance_classes(self) -> Annotated[list[str], "Conformance class URIs"]:  # type: ignore[empty-body]
        """A hook specification for declaring the OGC conformance classes a plugin satisfies.

        URIs follow the http://www.opengis.net/spec/... pattern and are aggregated
        into the `/conformance` endpoint.
        """
        pass

    @hookspec
    def ogc_collection_metadata(  # type: ignore[empty-body]
        self,
        collection_id: str,
        ds: xr.Dataset,
        deps: Dependencies,
    ) -> Annotated[dict[str, Any], "Metadata for a specific collection"]:
        """A hook specification for contributing keys to a collection object.

        Plugins may return arbitrary collection members (extent, parameter_names,
        crs, output_formats, ...) which are merged into the collection bodies
        served at `/collections` and `/collections/{collection_id}`.
        """
        pass

    @hookspec
    def ogc_collection_dataqueries(  # type: ignore[empty-body]
        self,
        collection_id: str,
        ds: xr.Dataset,
        deps: Dependencies,
    ) -> Annotated[dict[str, dict], "Data queries for a specific collection"]:
        """A hook specification for adding data queries to collection metadata."""
        pass


def ogc_exception(status_code: int, description: str) -> JSONResponse:
    """An error response satisfying both OGC exception schemas.

    OGC API - Common Part 1 exceptions are RFC 7807 problem details
    (`type` is required); OGC API - EDR's exception schema requires `code`
    instead. Both allow additional members, so the body carries both shapes.
    """
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "about:blank",
            "status": status_code,
            "detail": description,
            "code": str(status_code),
            "description": description,
        },
    )


class OGCExceptionRoute(APIRoute):
    """An ``APIRoute`` that renders errors as OGC exception objects.

    OGC API responses (including error responses) are validated against the
    official OGC schemas by the schemathesis fuzz tests and the CITE suites,
    and those schemas require error bodies to be OGC exception objects (a
    required ``code`` member; ``type`` for the RFC 7807 shape). FastAPI's
    default handlers return ``{"detail": ...}`` for both request validation
    errors and ``HTTPException``, which violates that schema.

    Set ``route_class=OGCExceptionRoute`` on an ``APIRouter`` to convert both
    through :func:`ogc_exception`, the same body ogc-core returns for its own
    errors. ``include_router`` preserves each route's own class, so OGC plugins
    must set this on the router they contribute via the ``ogc_router`` hook to
    get the behaviour on their endpoints.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        original_route_handler = super().get_route_handler()

        async def ogc_exception_route_handler(request: Request) -> Response:
            try:
                return await original_route_handler(request)
            except RequestValidationError as exc:
                description = (
                    "; ".join(
                        f"{'.'.join(str(loc) for loc in error['loc'])}: {error['msg']}"
                        for error in exc.errors()
                    )
                    or "Invalid request"
                )
                return ogc_exception(422, description)
            except HTTPException as exc:
                return ogc_exception(exc.status_code, str(exc.detail))

        return ogc_exception_route_handler


class OgcCorePlugin(Plugin):
    """OgcCorePlugin is a plugin that provides OGC Core functionality, and supports other OGC Xpublish plugins."""

    name: str = "ogc-core"
    app_router_tags: list[str | Enum] | None = ["OGC Core"]

    title: str = "Xpublish OGC API"
    description: str = "OGC API access to datasets served by Xpublish"

    @hookimpl
    def register_hookspec(self):
        """Register the OGC plugin specification."""
        return OgcPluginSpec

    @hookimpl
    def app_router(self, deps: Dependencies):
        """Register an application level router for OGC core endpoints, and mount additional OGC endpoints."""

        router = APIRouter(tags=self.app_router_tags, route_class=OGCExceptionRoute)

        for subrouter in deps.plugin_manager().hook.ogc_router(deps=deps):
            router.include_router(subrouter)

        def build_collection(collection_id: str, ds: xr.Dataset, base_url: str) -> dict[str, Any]:
            """Build a collection object: the OGC API - Common members from the
            dataset, then plugin contributions merged on top.

            Standard-specific members (e.g. EDR's extent/crs/parameter_names/
            output_formats requirements) are contributed by the plugins that
            implement those standards via the ogc_collection_metadata hook.
            """
            collection: dict[str, Any] = {
                "id": collection_id,
            }

            for key in ("title", "description", "attribution"):
                value = ds.attrs.get(key)
                if value is not None:
                    collection[key] = value

            keywords = ds.attrs.get("keywords")
            if isinstance(keywords, str):
                collection["keywords"] = [keyword.strip() for keyword in keywords.split(",")]
            elif keywords is not None:
                collection["keywords"] = list(keywords)

            crs = ds.attrs.get("crs")
            if isinstance(crs, str):
                collection["crs"] = [crs]
            elif crs is not None:
                collection["crs"] = list(crs)

            links = [
                Link(
                    href=urljoin(base_url, f"collections/{collection_id}"),
                    rel="self",
                    type="application/json",
                    title="This collection",
                ).model_dump(exclude_none=True),
                # each collection must link to itself with a `collection` (or
                # `data`) relation, cf. OGC API EDR 1.0 Abstract Test 15
                Link(
                    href=urljoin(base_url, f"collections/{collection_id}"),
                    rel="collection",
                    type="application/json",
                    title="This collection",
                ).model_dump(exclude_none=True),
            ]

            def absolutize(link: dict[str, Any]) -> dict[str, Any]:
                """Resolve root-relative hrefs from plugin contributions; clients
                (and the CITE test suites) can't reliably resolve relative links."""
                href = link.get("href", "")
                if href.startswith("/"):
                    link = {**link, "href": urljoin(base_url, href.lstrip("/"))}
                return link

            pm = deps.plugin_manager()

            for contribution in pm.hook.ogc_collection_metadata(
                collection_id=collection_id,
                ds=ds,
                deps=deps,
            ):
                if not contribution:
                    continue
                contribution = dict(contribution)
                links.extend(absolutize(link) for link in contribution.pop("links", []))
                collection.update(contribution)

            data_queries: dict[str, dict] = {}
            for dataquery in pm.hook.ogc_collection_dataqueries(
                collection_id=collection_id,
                ds=ds,
                deps=deps,
            ):
                if not dataquery:
                    continue
                for name, query in dataquery.items():
                    query = dict(query)
                    if "link" in query:
                        query["link"] = absolutize(query["link"])
                    data_queries[name] = query

            # data_queries is an EDR member, so it only appears when a plugin
            # describes some
            if data_queries:
                collection["data_queries"] = data_queries
            collection["links"] = links

            return collection

        @router.get(
            "/",
            summary="OGC API landing page",
            response_model=LandingPage,
            response_model_exclude_none=True,
        )
        def landing_page(request: Request) -> LandingPage:
            base_url = _base_url(request)

            return LandingPage(
                title=self.title,
                description=self.description,
                links=[
                    Link(
                        href=base_url,
                        rel="self",
                        type="application/json",
                        title="This document",
                    ),
                    Link(
                        href=urljoin(base_url, "openapi.json"),
                        rel="service-desc",
                        type="application/vnd.oai.openapi+json;version=3.0",
                        title="OpenAPI definition of this API",
                    ),
                    Link(
                        href=urljoin(base_url, "docs"),
                        rel="service-doc",
                        type="text/html",
                        title="Interactive documentation for this API",
                    ),
                    Link(
                        href=urljoin(base_url, "conformance"),
                        rel="conformance",
                        type="application/json",
                        title="OGC API conformance classes implemented by this server",
                    ),
                    Link(
                        href=urljoin(base_url, "conformance"),
                        rel=OGC_REL_CONFORMANCE,
                        type="application/json",
                        title="OGC API conformance classes implemented by this server",
                    ),
                    Link(
                        href=urljoin(base_url, "collections"),
                        rel="data",
                        type="application/json",
                        title="The collections served by this server",
                    ),
                    Link(
                        href=urljoin(base_url, "collections"),
                        rel=OGC_REL_DATA,
                        type="application/json",
                        title="The collections served by this server",
                    ),
                ],
            )

        @router.get(
            "/conformance",
            summary="OGC API conformance classes implemented by this server",
            response_model=ConfClasses,
        )
        def conformance() -> ConfClasses:
            conformance_classes = set(OGC_API_COMMON_CONFORMANCE_CLASSES)

            for plugin_classes in deps.plugin_manager().hook.ogc_conformance_classes():
                if plugin_classes:
                    conformance_classes.update(plugin_classes)

            return ConfClasses(conformsTo=sorted(conformance_classes))

        @router.get(
            "/collections",
            summary="The collections served by this server",
            response_model=Collections,
            response_model_exclude_none=True,
        )
        def collections(request: Request) -> Collections:
            base_url = _base_url(request)

            return Collections(
                links=[
                    Link(
                        href=urljoin(base_url, "collections"),
                        rel="self",
                        type="application/json",
                        title="This document",
                    ),
                ],
                collections=[
                    build_collection(collection_id, deps.dataset(collection_id), base_url)
                    for collection_id in deps.dataset_ids()
                ],
            )

        @router.get(
            "/collections/{collection_id}",
            summary="Get information about a specific collection.",
            responses={404: {"description": "Collection not found"}},
        )
        def collection_info(request: Request, collection_id: str):
            try:
                ds = deps.dataset(collection_id)
            except HTTPException as e:
                if e.status_code == 404:
                    return ogc_exception(404, f"Collection {collection_id!r} does not exist")
                raise

            return build_collection(collection_id, ds, _base_url(request))

        return router
