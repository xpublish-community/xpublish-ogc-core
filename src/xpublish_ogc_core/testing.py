"""Helpers for validating API responses against the official OGC schemas.

The schemas are vendored from the bundled OpenAPI document published by the
OGC API - Environmental Data Retrieval standard (see ``scripts/update_schemas.py``),
which also bundles the OGC API - Common building blocks (landingPage,
confClasses, collections, exception, ...).

Downstream OGC plugins can import :func:`validate_response` in their own test
suites to assert their responses follow the spec::

    from xpublish_ogc_core.testing import validate_response

    validate_response("landingPage", client.get("/").json())
"""

import json
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT7

BUNDLED_SCHEMA_FILENAME = "ogcapi-environmental-data-retrieval-1-oas30.bundled.json"

# URI used to register the bundled document with the referencing registry so
# `#/components/schemas/...` pointers resolve against it
_BASE_URI = f"urn:xpublish-ogc-core:{BUNDLED_SCHEMA_FILENAME}"


@lru_cache(maxsize=None)
def bundled_document() -> dict:
    """Load the vendored OGC bundled OpenAPI document."""
    schema_path = resources.files("xpublish_ogc_core") / "schemas" / BUNDLED_SCHEMA_FILENAME
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


@lru_cache(maxsize=None)
def _registry() -> Registry:
    """A referencing registry rooted at the bundled document."""
    resource = Resource.from_contents(bundled_document(), default_specification=DRAFT7)
    return Registry().with_resource(_BASE_URI, resource)


def component_schema(name: str) -> dict:
    """Return component schema ``name`` wrapped so internal ``$ref``s resolve.

    The returned schema references ``#/components/schemas/{name}`` within the
    bundled document, and is ready to pass to a :mod:`jsonschema` validator
    along with the registry used by :func:`validate_response`.
    """
    components = bundled_document()["components"]["schemas"]
    if name not in components:
        raise KeyError(
            f"{name!r} is not a component schema in {BUNDLED_SCHEMA_FILENAME}; "
            f"available schemas: {sorted(components)}",
        )

    return {"$ref": f"{_BASE_URI}#/components/schemas/{name}"}


def validate_response(name: str, data: Any) -> None:
    """Assert that a JSON response body validates against component schema ``name``.

    Raises an :class:`AssertionError` carrying the jsonschema error messages so
    test failures point at the exact spec violation.
    """
    validator = jsonschema.Draft7Validator(
        component_schema(name),
        registry=_registry(),
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
