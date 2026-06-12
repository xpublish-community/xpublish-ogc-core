"""Run official OGC CITE executable test suites against a live Xpublish app.

The suites are executed by `OGC TeamEngine <https://opengeospatial.github.io/teamengine/>`_
running in the official ``ogccite/ets-*`` Docker images, driven through
TeamEngine's REST API. Downstream OGC plugins use this in their test suites::

    from xpublish_ogc_core import teamengine

    with (
        teamengine.serve_app(rest.app) as app_url,
        teamengine.teamengine_container(
            "ogccite/ets-ogcapi-edr10:1.3-teamengine-6.0.0-RC2"
        ) as engine_url,
    ):
        result = teamengine.run_suite(
            engine_url,
            "ogcapi-edr10",
            {"iut": app_url, "apiDefinition": f"{app_url}/openapi.json"},
        )

    assert not result.failure_names(), result.summary()

Requires the ``docker`` CLI; tests should skip when it isn't available (see
:func:`docker_available`).
"""

import contextlib
import shutil
import socket
import subprocess
import threading
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from xml.etree import ElementTree

import fastapi

# the host as seen from inside a container, provided by Docker Desktop and
# mapped explicitly on Linux via --add-host below
DOCKER_HOST_GATEWAY = "host.docker.internal"

# default credentials of the user shipped with the ogccite images
DEFAULT_CREDENTIALS = ("ogctest", "ogctest")


def docker_available() -> bool:
    """Whether the docker CLI is available and the daemon is responding."""
    if shutil.which("docker") is None:
        return False

    try:
        subprocess.run(
            ["docker", "version"],
            capture_output=True,
            check=True,
            timeout=30,
        )
    except (subprocess.SubprocessError, OSError):
        return False

    return True


def free_port() -> int:
    """Ask the OS for an unused TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def serve_app(app, port: int | None = None) -> Iterator[str]:
    """Serve an ASGI app over real HTTP in a background thread.

    Yields the app's base URL as seen from inside a Docker container, without
    a trailing slash: the CITE suites concatenate paths like ``/collections``
    directly onto the ``iut`` value.
    """
    import uvicorn

    port = port or free_port()
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.monotonic() + 30
    while not server.started:
        if time.monotonic() > deadline or not thread.is_alive():
            raise RuntimeError("uvicorn server did not start within 30 seconds")
        time.sleep(0.05)

    try:
        yield f"http://{DOCKER_HOST_GATEWAY}:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)


@contextlib.contextmanager
def teamengine_container(
    image: str,
    port: int | None = None,
    startup_timeout: float = 600,
) -> Iterator[str]:
    """Run a TeamEngine CITE image, yielding its base REST URL once responsive.

    The image is pulled on first use, which can take a while. The generous
    startup timeout accounts for the amd64-only images booting under
    emulation on other architectures.
    """
    import httpx

    port = port or free_port()

    container_id = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--detach",
            # make host.docker.internal resolve on Linux; Docker Desktop
            # provides it natively and ignores the duplicate
            "--add-host",
            f"{DOCKER_HOST_GATEWAY}:host-gateway",
            "--publish",
            f"{port}:8080",
            image,
        ],
        capture_output=True,
        check=True,
        text=True,
    ).stdout.strip()

    base_url = f"http://127.0.0.1:{port}/teamengine"

    try:
        deadline = time.monotonic() + startup_timeout
        while True:
            try:
                response = httpx.get(f"{base_url}/", follow_redirects=True, timeout=5)
                if response.status_code == 200:
                    break
            except httpx.HTTPError:
                pass

            if time.monotonic() > deadline:
                raise RuntimeError(
                    f"TeamEngine at {base_url} did not become ready "
                    f"within {startup_timeout} seconds",
                )
            time.sleep(2)

        yield base_url
    finally:
        subprocess.run(
            ["docker", "stop", container_id],
            capture_output=True,
            check=False,
        )


@dataclass
class FailedTest:
    """A single failed CITE test, e.g. ``ApiDefinition.apiDefinitionValidation``."""

    name: str
    message: str


@dataclass
class SuiteResult:
    """Outcome of a TeamEngine suite run, parsed from TestNG results XML."""  # codespell:ignore

    passed: int = 0
    failed: int = 0
    skipped: int = 0
    failures: list[FailedTest] = field(default_factory=list)

    def failure_names(self) -> set[str]:
        return {failure.name for failure in self.failures}

    def summary(self) -> str:
        lines = [
            f"{self.passed} passed, {self.failed} failed, {self.skipped} skipped",
        ]
        lines.extend(f"  FAIL {failure.name}: {failure.message}" for failure in self.failures)
        return "\n".join(lines)


def parse_testng_results(xml_text: str) -> SuiteResult:
    """Parse TeamEngine's TestNG results XML into a :class:`SuiteResult`."""  # codespell:ignore
    root = ElementTree.fromstring(xml_text)

    result = SuiteResult()
    for test_class in root.iter("class"):
        class_name = test_class.get("name", "").rsplit(".", 1)[-1]

        for test_method in test_class.findall("test-method"):
            if test_method.get("is-config") == "true":
                continue

            status = test_method.get("status", "")
            if status == "PASS":
                result.passed += 1
            elif status == "FAIL":
                result.failed += 1

                exception = test_method.find(".//exception/message")
                message = exception.text.strip() if exception is not None and exception.text else ""
                result.failures.append(
                    FailedTest(
                        name=f"{class_name}.{test_method.get('name', '')}",
                        message=message,
                    ),
                )
            elif status == "SKIP":
                result.skipped += 1

    return result


def run_suite(
    teamengine_url: str,
    suite: str,
    params: dict[str, str],
    auth: tuple[str, str] = DEFAULT_CREDENTIALS,
    timeout: float = 1800,
) -> SuiteResult:
    """Execute a CITE suite via TeamEngine's REST API and parse the results.

    ``params`` are the suite's test run properties (e.g. ``{"iut": app_url}``).
    Mind that URI-valued properties should not end with a trailing slash, and
    that the EDR suite reports a missing ``apiDefinition`` with a misleading
    "Absolute URI is required, but received" error.
    """
    import httpx

    response = httpx.get(
        f"{teamengine_url}/rest/suites/{suite}/run",
        params=params,
        headers={"Accept": "application/xml"},
        auth=auth,
        timeout=timeout,
    )
    response.raise_for_status()

    return parse_testng_results(response.text)


def run_suite_with_app(
    suite: str,
    app: "fastapi.FastAPI",
    params: dict[str, str],
    ets_image: str,
    auth: tuple[str, str] = DEFAULT_CREDENTIALS,
    timeout: float = 1800,
) -> SuiteResult:
    """Convenience wrapper to run a test suite against an ASGI app."""
    with (
        serve_app(app) as app_url,
        teamengine_container(ets_image) as engine_url,
    ):
        return run_suite(
            teamengine_url=engine_url,
            suite=suite,
            params={**params, "iut": app_url, "apiDefinition": f"{app_url}/openapi.json"},
            auth=auth,
            timeout=timeout,
        )
