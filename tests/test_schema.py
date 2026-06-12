"""Fuzz the OGC core endpoints against the app's own OpenAPI description and the OGC specs."""

import schemathesis
import xpublish
from conftest import FakeOgcPlugin

from xpublish_ogc_core import testing
from xpublish_ogc_core.plugin import OgcCorePlugin


def build_app():
    from cf_xarray.datasets import airds

    rest = xpublish.Rest(
        {"air": airds},
        plugins={
            "ogc": OgcCorePlugin(),
            "fake": FakeOgcPlugin(),
        },
    )
    return rest.app


plugin_schema = schemathesis.openapi.from_asgi("/openapi.json", build_app())

ogc_schema = (
    testing.bundled_schema(with_app=build_app())
    .exclude(path_regex=r"^/collections/\{collectionId\}/items")
    .exclude(path_regex=r"^/collections/\{collectionId\}/instances")
    .exclude(path_regex=r"^/collections/\{collectionId\}/locations")
    .exclude(path_regex=r"^/collections/\{collectionId\}/position")
    .exclude(path_regex=r"^/collections/\{collectionId\}/area")
    .exclude(path_regex=r"^/collections/\{collectionId\}/cube")
    .exclude(path_regex=r"^/collections/\{collectionId\}/radius")
    .exclude(path_regex=r"^/collections/\{collectionId\}/trajectory")
    .exclude(path_regex=r"^/collections/\{collectionId\}/corridor")
)


@schemathesis.pytest.parametrize(
    plugin=plugin_schema,
    ogc=ogc_schema,
)
def test_ogc_api(case):
    case.call_and_validate()
