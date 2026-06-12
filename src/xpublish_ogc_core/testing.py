"""Helpers for validating API responses against the official OGC schemas.

The schemas are vendored by ``scripts/update_schemas.py`` in two forms:

- bundled OpenAPI documents published by individual OGC API standards:
  ``"edr"`` (which also carries that standard's renditions of the OGC API -
  Common building blocks) and ``"tiles"``, validated through their
  ``#/components/schemas`` (and ``#/components/responses`` JSON content);
- ``"common"``: the standalone OGC API - Common Part 1 building blocks
  (landingPage, confClasses, exception, link) plus the collections shapes
  from OGC API - Features Part 1, which the unpublished Common Part 2
  derives from.

Downstream OGC plugins can import :func:`validate_response` in their own test
suites to assert their responses follow the spec::

    from xpublish_ogc_core.testing import validate_response

    validate_response("landingPage", client.get("/").json(), document="common")
    validate_response("collection", client.get("/collections/air").json())
    validate_response("tileSet", ..., document="tiles")
"""

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

BUNDLED_DOCUMENTS = {
    "edr": "ogcapi-environmental-data-retrieval-1-oas30.bundled.json",
    "tiles": "ogcapi-tiles-1.bundled.json",
}

# documents made of standalone schema files, described by a manifest mapping
# component names to files and files to their canonical source URIs
SCHEMA_FILE_DOCUMENTS = {
    "common": "common",
}

DEFAULT_DOCUMENT = "edr"


def _schemas_root():
    return resources.files("xpublish_ogc_core") / "schemas"


def _base_uri(document: str) -> str:
    """URI used to register a bundled document with the referencing registry
    so `#/components/...` pointers resolve against it"""
    return f"urn:xpublish-ogc-core:{BUNDLED_DOCUMENTS[document]}"


@lru_cache(maxsize=None)
def bundled_document(document: str = DEFAULT_DOCUMENT) -> dict:
    """Load a vendored OGC bundled OpenAPI document."""
    if document not in BUNDLED_DOCUMENTS:
        raise KeyError(
            f"{document!r} is not a vendored OGC bundle; "
            f"available bundles: {sorted(BUNDLED_DOCUMENTS)}",
        )

    schema_path = _schemas_root() / BUNDLED_DOCUMENTS[document]
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _manifest(document: str) -> dict:
    """Load the manifest of a standalone schema file document."""
    manifest_path = _schemas_root() / SCHEMA_FILE_DOCUMENTS[document] / "manifest.json"
    with manifest_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _registry(document: str) -> Registry:
    """A referencing registry covering the document's schemas.

    Bundled documents register the whole document under a single URI;
    schema file documents register every file under its canonical source
    URI, so the relative refs between them (`link.json`, `extent.json`, ...)
    resolve within the registry without touching the network.
    """
    if document in BUNDLED_DOCUMENTS:
        resource = Resource.from_contents(
            bundled_document(document),
            default_specification=DRAFT7,
        )
        return Registry().with_resource(_base_uri(document), resource)

    document_dir = _schemas_root() / SCHEMA_FILE_DOCUMENTS[document]
    registry = Registry()
    for path, uri in _manifest(document)["resources"].items():
        with (document_dir / path).open("r", encoding="utf-8") as f:
            resource = Resource.from_contents(
                json.load(f),
                default_specification=DRAFT7,
            )
        registry = registry.with_resource(uri, resource)
    return registry


def component_schema(name: str, document: str = DEFAULT_DOCUMENT) -> dict:
    """Return component schema ``name`` wrapped so internal ``$ref``s resolve.

    For bundled documents the returned schema references
    ``#/components/schemas/{name}`` (or the JSON content schema of
    ``#/components/responses/{name}``); for schema file documents it
    references the file registered for ``name``. Either way it is ready to
    pass to a :mod:`jsonschema` validator along with the registry used by
    :func:`validate_response`.
    """
    if document in SCHEMA_FILE_DOCUMENTS:
        components = _manifest(document)["components"]
        if name not in components:
            raise KeyError(
                f"{name!r} is not a component schema in the {document!r} document; "
                f"available schemas: {sorted(components)}",
            )
        return {"$ref": _manifest(document)["resources"][components[name]]}

    components = bundled_document(document)["components"]
    base_uri = _base_uri(document)

    if name in components.get("schemas", {}):
        return {"$ref": f"{base_uri}#/components/schemas/{name}"}

    response = components.get("responses", {}).get(name, {})
    if "schema" in response.get("content", {}).get("application/json", {}):
        # `/` in the media type is escaped as `~1` per the JSON pointer spec
        return {
            "$ref": (
                f"{base_uri}#/components/responses/{name}"
                "/content/application~1json/schema"
            ),
        }

    raise KeyError(
        f"{name!r} is not a component schema or JSON response "
        f"in {BUNDLED_DOCUMENTS[document]}; "
        f"available schemas: {sorted(components.get('schemas', {}))}; "
        f"available responses: {sorted(components.get('responses', {}))}",
    )


def validate_response(name: str, data: Any, document: str = DEFAULT_DOCUMENT) -> None:
    """Assert that a JSON response body validates against component schema ``name``.

    Raises an :class:`AssertionError` carrying the jsonschema error messages so
    test failures point at the exact spec violation.
    """
    validator = jsonschema.Draft7Validator(
        component_schema(name, document),
        registry=_registry(document),
    )

    errors = sorted(
        validator.iter_errors(data),
        key=lambda error: list(error.absolute_path),
    )
    if errors:
        details = "\n".join(
            f"  {error.json_path}: {error.message}" for error in errors
        )
        raise AssertionError(
            f"Response body does not validate against OGC component schema {name!r}:\n{details}",
        )
