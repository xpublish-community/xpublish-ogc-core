"""Tests for the schema validation helpers shipped for downstream OGC plugins."""

import pytest

from xpublish_ogc_core.testing import (
    BUNDLED_DOCUMENTS,
    bundled_document,
    component_schema,
    validate_response,
)


@pytest.mark.parametrize("document", sorted(BUNDLED_DOCUMENTS))
def test_bundled_documents_load(document):
    doc = bundled_document(document)

    assert doc["openapi"].startswith("3.0"), "Bundles should be OAS 3.0 documents"
    assert "schemas" in doc["components"]


def test_unknown_document():
    with pytest.raises(KeyError, match="not a vendored OGC bundle"):
        bundled_document("not-a-standard")


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("landingPage", "edr"),
        ("confClasses", "edr"),
        ("collection", "edr"),
        ("confClasses", "tiles"),
        ("tileMatrixSet", "tiles"),
        ("tileSet", "tiles"),
    ],
)
def test_component_schema(name, document):
    schema = component_schema(name, document)

    assert schema["$ref"].endswith(f"#/components/schemas/{name}")


@pytest.mark.parametrize(
    "name",
    [
        "landingPage",
        "confClasses",
        "exception",
        "link",
        "collections",
        "collection",
        "extent",
    ],
)
def test_common_component_schema(name):
    """The Common document is standalone schema files, referenced by source URI."""
    schema = component_schema(name, "common")

    assert schema["$ref"].startswith("https://schemas.opengis.net/")


def test_common_validation_resolves_refs_between_files():
    """collections -> collection -> link refs resolve across the vendored files."""
    validate_response(
        "collections",
        {
            "links": [{"href": "https://example.org/collections", "rel": "self"}],
            "collections": [
                {
                    "id": "air",
                    "links": [
                        {"href": "https://example.org/collections/air", "rel": "self"}
                    ],
                },
            ],
        },
        document="common",
    )

    with pytest.raises(AssertionError, match="'id' is a required property"):
        validate_response(
            "collections",
            {"links": [], "collections": [{"links": []}]},
            document="common",
        )


@pytest.mark.parametrize(
    ("name", "document"),
    [
        ("TileSetsList", "tiles"),
        ("TileMatrixSetsList", "tiles"),
    ],
)
def test_component_schema_from_responses(name, document):
    """List shapes only described in components/responses are reachable too."""
    schema = component_schema(name, document)

    assert "/components/responses/" in schema["$ref"]


def test_unknown_component_schema():
    with pytest.raises(KeyError, match="not a component schema"):
        component_schema("not-a-schema", "tiles")


@pytest.mark.parametrize("document", sorted(BUNDLED_DOCUMENTS))
def test_validate_response_accepts_valid_conformance(document):
    validate_response("confClasses", {"conformsTo": ["http://..."]}, document)


@pytest.mark.parametrize("document", sorted(BUNDLED_DOCUMENTS))
def test_validate_response_raises_with_spec_violation(document):
    with pytest.raises(AssertionError, match="conformsTo"):
        validate_response("confClasses", {}, document)


def test_validate_response_resolves_nested_refs():
    """Validation follows $refs within the bundled document."""
    tilesets = {"tilesets": [{"title": "missing required keys"}]}

    with pytest.raises(AssertionError, match="dataType"):
        validate_response("TileSetsList", tilesets, "tiles")
