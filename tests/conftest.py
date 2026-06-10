from typing import Any, Dict

import pytest
import xarray as xr
import xpublish
from fastapi import APIRouter
from fastapi.testclient import TestClient
from xpublish import Dependencies, Plugin, hookimpl

from xpublish_ogc_core.plugin import OgcCorePlugin

FAKE_CONFORMANCE_CLASS = "http://www.opengis.net/spec/fake-ogc-1/1.0/conf/core"


class FakeOgcPlugin(Plugin):
    """A stub OGC plugin exercising every OGC hookspec without depending on a real standard."""

    name: str = "fake-ogc"

    @hookimpl
    def ogc_router(self, deps: Dependencies):
        router = APIRouter(tags=["Fake OGC"])

        @router.get(
            "/collections/{collection_id}/fake",
            summary="A stub data query",
        )
        def fake_query(collection_id: str) -> Dict[str, str]:
            return {"collection_id": collection_id}

        return router

    @hookimpl
    def ogc_conformance_classes(self):
        return [FAKE_CONFORMANCE_CLASS]

    @hookimpl
    def ogc_collection_metadata(self, collection_id: str, ds: xr.Dataset) -> Dict[str, Any]:
        return {
            "extent": {
                "spatial": {
                    "bbox": [[200.0, 15.0, 322.5, 75.0]],
                    "crs": "EPSG:4326",
                },
            },
            "crs": ["EPSG:4326"],
            "output_formats": ["application/json"],
            "parameter_names": {
                "air": {
                    "type": "Parameter",
                    "observedProperty": {"label": "air_temperature"},
                },
            },
        }

    @hookimpl
    def ogc_collection_dataqueries(self, collection_id: str, ds: xr.Dataset) -> Dict[str, Dict]:
        return {
            "position": {
                "link": {
                    "href": f"/collections/{collection_id}/fake",
                    "rel": "data",
                    "type": "application/json",
                    "hreflang": "en",
                    "title": "Fake position query",
                    "variables": {
                        "title": "Fake position query",
                        "description": "A stub data query for testing the OGC hook plumbing",
                        "query_type": "position",
                        "output_formats": ["application/json"],
                        "default_output_format": "application/json",
                        "crs_details": [
                            {"crs": "EPSG:4326", "wkt": "GEOGCS[...]"},
                        ],
                    },
                },
            },
        }


@pytest.fixture(scope="session")
def air_dataset():
    from cf_xarray.datasets import airds

    return airds


@pytest.fixture(scope="session")
def rest(air_dataset):
    return xpublish.Rest(
        {"air": air_dataset},
        plugins={
            "ogc": OgcCorePlugin(),
            "fake": FakeOgcPlugin(),
        },
    )


@pytest.fixture(scope="session")
def app(rest):
    return rest.app


@pytest.fixture(scope="session")
def client(app):
    return TestClient(app)
