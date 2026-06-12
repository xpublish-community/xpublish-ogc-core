"""Official OGC CITE compliance testing of the core plugin itself.

There is no executable test suite for OGC API - Common, so the OGC API - EDR
suite is run against the core plugin composed with the stub OGC plugin: its
Common subset (landing page, api definition, conformance declaration, and
collections structure) directly exercises the endpoints this plugin serves,
while the EDR-specific tests skip or land in the known-failures list.

Requires Docker (the image is pulled on first use); skipped otherwise.
Deselect with `-m "not cite"`.
"""

import pytest
import xpublish
from conftest import FakeOgcPlugin

from xpublish_ogc_core import teamengine
from xpublish_ogc_core.plugin import OgcCorePlugin

pytestmark = [
    pytest.mark.cite,
    pytest.mark.skipif(
        not teamengine.docker_available(),
        reason="requires the docker CLI and a running daemon",
    ),
]

ETS_IMAGE = "ogccite/ets-ogcapi-edr10:1.3-teamengine-6.0.0-RC2"
SUITE = "ogcapi-edr10"

KNOWN_FAILURES = {
    # FastAPI generates an OpenAPI 3.1 document, while the suite validates it
    # against OpenAPI 3.0 and rejects the `"type": "null"` members that
    # pydantic emits for optional fields
    "ApiDefinition.apiDefinitionValidation",
    # the suite requires the EDR core conformance class, which a server
    # without the EDR plugin correctly does not declare
    "Conformance.validateConformanceOperationAndResponse",
}


def test_common_subset_of_edr_cite_suite(air_dataset):
    rest = xpublish.Rest(
        {"air": air_dataset},
        plugins={"ogc": OgcCorePlugin(), "fake": FakeOgcPlugin()},
    )

    with (
        teamengine.serve_app(rest.app) as app_url,
        teamengine.teamengine_container(ETS_IMAGE) as engine_url,
    ):
        result = teamengine.run_suite(
            engine_url,
            SUITE,
            {
                "iut": app_url,
                "apiDefinition": f"{app_url}/openapi.json",
            },
        )

    unexpected = result.failure_names() - KNOWN_FAILURES
    assert not unexpected, f"Unexpected CITE failures:\n{result.summary()}"

    fixed = KNOWN_FAILURES - result.failure_names()
    assert not fixed, f"Known failures now pass, remove them from KNOWN_FAILURES: {sorted(fixed)}"

    assert result.passed >= 9, f"Suite did not run as expected:\n{result.summary()}"
