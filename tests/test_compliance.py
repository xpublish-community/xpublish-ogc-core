"""Validate every OGC core endpoint against the vendored official OGC schemas."""

from conftest import FAKE_CONFORMANCE_CLASS

from xpublish_ogc_core.plugin import OGC_API_COMMON_CONFORMANCE_CLASSES
from xpublish_ogc_core.testing import validate_response


def link_rels(data) -> set:
    return {link["rel"] for link in data["links"]}


def test_landing_page(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    validate_response("landingPage", data)

    rels = link_rels(data)
    for rel in (
        "self",
        "service-desc",
        "service-doc",
        "conformance",
        "data",
        "http://www.opengis.net/def/rel/ogc/1.0/conformance",
        "http://www.opengis.net/def/rel/ogc/1.0/data",
    ):
        assert rel in rels, f"Landing page should include a {rel!r} link"


def test_conformance(client):
    response = client.get("/conformance")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    validate_response("confClasses", data)

    for conformance_class in OGC_API_COMMON_CONFORMANCE_CLASSES:
        assert conformance_class in data["conformsTo"]

    assert FAKE_CONFORMANCE_CLASS in data["conformsTo"], (
        "Conformance classes from the ogc_conformance_classes hook should be aggregated"
    )

    assert data["conformsTo"] == sorted(set(data["conformsTo"]))


def test_collections(client):
    response = client.get("/collections")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    validate_response("collections", data)

    assert "self" in link_rels(data)

    collection_ids = [collection["id"] for collection in data["collections"]]
    assert collection_ids == ["air"]


def test_collection(client):
    response = client.get("/collections/air")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/json"

    data = response.json()
    validate_response("collection", data)

    assert data["id"] == "air"
    assert "self" in link_rels(data)

    # contributions from the fake plugin's ogc_collection_metadata hook
    assert data["extent"]["spatial"]["bbox"] == [[200.0, 15.0, 322.5, 75.0]]
    assert data["crs"] == ["EPSG:4326"]
    assert data["output_formats"] == ["application/json"]
    assert "air" in data["parameter_names"]

    # contributions from the fake plugin's ogc_collection_dataqueries hook,
    # with relative hrefs made absolute
    assert (
        data["data_queries"]["position"]["link"]["href"]
        == "http://testserver/collections/air/fake"
    )


def test_unknown_collection_returns_ogc_exception(client):
    response = client.get("/collections/not-a-collection")

    assert response.status_code == 404

    data = response.json()
    validate_response("exception", data)


def test_ogc_router_hook_mounted(client):
    response = client.get("/collections/air/fake")

    assert response.status_code == 200
    assert response.json() == {"collection_id": "air"}
