from typing import Annotated, List, Dict

from fastapi import APIRouter
import xarray as xr
from xpublish import Dependencies, Plugin, hookimpl, hookspec as hookspec


class OgcPluginSpec(Plugin):
    """A specification for OGC plugins."""

    @hookspec
    def ogc_router(self, deps: Dependencies) -> Annotated[APIRouter, "An OGC specific router"]:
        """A hook specification for adding OGC specific routers."""
        pass

    @hookspec
    def ogc_collection_dataqueries(self, collection_id: str, ds: xr.Dataset) -> Annotated[Dict[str, Dict], "Data queries for a specific collection"]:
        """A hook specification for adding data queries to collection metadata."""
        pass


class OgcCorePlugin(Plugin):
    """OgcCorePlugin is a plugin that provides OGC Core functionality, and supports other OGC Xpublish plugins."""

    name: str = "ogc-core"
    app_router_tags: List[str] = ["OGC Core"]

    @hookimpl
    def register_hookspec(self):
        """Register the OGC plugin specification."""
        return OgcPluginSpec

    @hookimpl
    def app_router(self, deps: Dependencies):
        """Regster an application level router for OGC core endpoints, and mount additional OGC endpoints."""

        router = APIRouter(tags=self.app_router_tags)

        for subrouter in deps.plugin_manager().hook.ogc_router(deps=deps):
            router.include_router(subrouter)

        @router.get("/collections", summary="A list of all collection in this dataset.")
        def collections():
            datasets = deps.dataset_ids()
            return {
                "links": [],
                "collections": datasets,
            }
        
        @router.get("/collections/{collection_id}", summary="Get information about a specific collection.")
        def collection_info(collection_id: str):
            ds = deps.dataset(collection_id)
            meta = {"id": collection_id, "links": [], "extent": {}, "output_formats": [], "parameter_names": {}}

            for key in ["title", "description", "keywords", "crs", "attribution"]:
                value = ds.attrs.get(key)
                if value is not None:
                    meta[key] = value

            data_queries = {}

            for dq in deps.plugin_manager().hook.ogc_collection_dataqueries(collection_id=collection_id, ds=ds):
                data_queries.update(dq)

            meta["data_queries"] = data_queries

            return meta
        
        return router
    