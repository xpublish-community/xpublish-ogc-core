"""Tests for OGCExceptionRoute.

FastAPI's default error handlers return ``{"detail": ...}`` for request
validation errors and ``HTTPException``, which violates the OGC exception
schema (a required ``code`` member). ``OGCExceptionRoute`` converts both into
``ogc_exception`` bodies so error responses validate against the OGC schemas.
"""

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.testclient import TestClient

from xpublish_ogc_core.plugin import OGCExceptionRoute
from xpublish_ogc_core.testing import validate_response


def _client() -> TestClient:
    router = APIRouter(route_class=OGCExceptionRoute)

    @router.get("/needs-param")
    def needs_param(value: int) -> dict[str, int]:
        return {"value": value}

    @router.get("/raises")
    def raises() -> dict[str, str]:
        raise HTTPException(status_code=404, detail="nothing here")

    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def test_request_validation_error_is_ogc_exception():
    """A 422 from request validation is rendered as an OGC exception object."""
    response = _client().get("/needs-param", params={"value": "not-an-int"})

    assert response.status_code == 422
    data = response.json()
    # the official OGC exception schema requires a string `code` member, which
    # FastAPI's default `{"detail": [...]}` body does not provide
    assert data["code"] == "422"
    assert "value" in data["description"]
    validate_response("exception", data)


def test_missing_required_param_is_ogc_exception():
    """A missing required query parameter also yields an OGC exception object."""
    response = _client().get("/needs-param")

    assert response.status_code == 422
    data = response.json()
    assert data["code"] == "422"
    validate_response("exception", data)


def test_http_exception_is_ogc_exception():
    """An HTTPException raised in the handler is rendered as an OGC exception."""
    response = _client().get("/raises")

    assert response.status_code == 404
    data = response.json()
    assert data["code"] == "404"
    assert data["description"] == "nothing here"
    validate_response("exception", data)
