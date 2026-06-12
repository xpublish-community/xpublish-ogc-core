"""Generic OGC API - Common response models.

Only the building blocks shared by all OGC API standards live here; standard
specific models (e.g. EDR collection metadata) belong in the plugins that
implement those standards.
"""

from typing import Any

from pydantic import BaseModel


class OGCException(BaseModel):
    """An OGC API error body.

    Carries both error shapes the OGC schemas accept: OGC API - Common Part 1
    uses RFC 7807 problem details (``type``/``status``/``detail``), while OGC
    API - EDR requires ``code``. :func:`xpublish_ogc_core.plugin.ogc_exception`
    produces this body, and :class:`~xpublish_ogc_core.plugin.OGCExceptionRoute`
    reshapes errors into it; declare it on a route's ``responses`` so the
    OpenAPI document matches what those error responses actually return.
    """

    code: str
    description: str | None = None
    type: str | None = None
    status: int | None = None
    detail: str | None = None


class Link(BaseModel):
    """A link following OGC API and RFC 8288 (Web Linking) conventions.

    https://docs.ogc.org/is/19-072/19-072.html
    """

    href: str
    rel: str
    type: str | None = None
    hreflang: str | None = None
    title: str | None = None
    length: int | None = None
    templated: bool | None = None


class LandingPage(BaseModel):
    """OGC API landing page.

    https://docs.ogc.org/is/19-072/19-072.html#_b8a2980d-7bb6-4f7f-adac-d3b15a2eba1c
    """

    title: str | None = None
    description: str | None = None
    links: list[Link]


class ConfClasses(BaseModel):
    """OGC API conformance declaration.

    https://docs.ogc.org/is/19-072/19-072.html#_4d80586c-c7c7-4b4e-a6a8-7c8be83033b6
    """

    conformsTo: list[str]


class Collections(BaseModel):
    """OGC API collections response.

    Collection bodies are extended by plugins via the ``ogc_collection_metadata``
    and ``ogc_collection_dataqueries`` hooks, so they stay open dictionaries.
    """

    links: list[Link]
    collections: list[dict[str, Any]]
