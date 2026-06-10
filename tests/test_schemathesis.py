"""Fuzz the OGC core endpoints against the app's own OpenAPI description."""

import schemathesis

from conftest import FakeOgcPlugin

import xpublish
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


schema = schemathesis.openapi.from_asgi("/openapi.json", build_app()).include(
    path_regex=r"^/(collections|conformance|$)",
)


@schema.parametrize()
def test_ogc_api(case):
    case.call_and_validate()
