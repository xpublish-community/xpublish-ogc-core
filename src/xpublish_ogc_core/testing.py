"""Helpers for validating API responses against the official OGC schemas.

The schemas are vendored from the bundled OpenAPI documents published by the
OGC API standards (see ``scripts/update_schemas.py``). The EDR bundle also
carries the OGC API - Common building blocks (landingPage, confClasses,
collections, exception, ...), and the Tiles bundle carries the OGC API - Tiles
building blocks (tileSet, tileMatrixSet, ...).

Downstream OGC plugins can import :func:`validate_response` in their own test
suites to assert their responses follow the spec::

    from xpublish_ogc_core.testing import validate_response

    validate_response("landingPage", client.get("/").json())
    validate_response("tileSet", client.get(...).json(), document="tiles")

Schemas are looked up in the document's ``components/schemas`` first; names
not found there fall back to the JSON content schema of the same-named entry
in ``components/responses`` (some bundles only describe list responses there,
e.g. ``TileSetsList`` in the Tiles bundle).
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

DEFAULT_DOCUMENT = "edr"


def _base_uri(document: str) -> str:
    """URI used to register a bundled document with the referencing registry
    so `#/components/...` pointers resolve against it"""
    return f"urn:xpublish-ogc-core:{BUNDLED_DOCUMENTS[document]}"


@lru_cache(maxsize=None)
def bundled_document(document: str = DEFAULT_DOCUMENT) -> dict:
    """Load a vendored OGC bundled OpenAPI document."""
    if document not in BUNDLED_DOCUMENTS:
        raise KeyError(
            f"{document!r} is not a vendored OGC document; "
            f"available documents: {sorted(BUNDLED_DOCUMENTS)}",
        )

    filename = BUNDLED_DOCUMENTS[document]
    schema_path = resources.files("xpublish_ogc_core") / "schemas" / filename
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _registry(document: str) -> Registry:
    """A referencing registry rooted at the bundled document."""
    resource = Resource.from_contents(
        bundled_document(document),
        default_specification=DRAFT7,
    )
    return Registry().with_resource(_base_uri(document), resource)


def component_schema(name: str, document: str = DEFAULT_DOCUMENT) -> dict:
    """Return component schema ``name`` wrapped so internal ``$ref``s resolve.

    The returned schema references ``#/components/schemas/{name}`` (or the
    JSON content schema of ``#/components/responses/{name}``) within the
    bundled document, and is ready to pass to a :mod:`jsonschema` validator
    along with the registry used by :func:`validate_response`.
    """
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
