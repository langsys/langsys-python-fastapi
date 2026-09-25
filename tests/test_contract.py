"""Rows proven against the shared contract double (spec CONF-2).

`tests/contract-fixture/` is the fleet's one HTTP double, vendored byte-exact (tree `542f57f5`) with
the core's harness (`tests/contract.py`). It says no the way the API does, computes
`write_enabled` itself, and exposes only accepted state, so every assertion here reads back what
the double accepted.
"""

from __future__ import annotations

import asyncio
import shutil
from typing import Any, Optional

import pytest
from contract import IP_WRITE_KEY, PROJECT, READ_KEY, WRITE_KEY, ContractDouble, world
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from langsys.cache import MemoryCache
from pydantic import BaseModel, Field
from test_request_boundary import drive

from langsys_fastapi import LangsysMiddleware, configure, get_client, t
from langsys_fastapi.locale import get_current_locale
from langsys_fastapi.messages import install

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="the double needs Node 18+")


@pytest.fixture(scope="module")
def double():
    running = ContractDouble()
    yield running
    running.close()


@pytest.fixture()
def session(double):
    started: list[Any] = []

    def start(key: str, **seed: Any) -> Any:
        double.seed(world(**seed))
        configure(api_key=key, project_id=PROJECT, api_url=double.base_url, cache=MemoryCache())
        started.append(get_client())
        return started[-1]

    yield start
    if started:
        get_client().clear_pending()
    configure()


def locale_app(vary: Optional[str] = None, **options: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware, **options)

    @app.get("/page")
    def page(response: Response):
        if vary:
            response.headers["Vary"] = vary
        return {"locale": get_current_locale().lower()}

    return app


def varies(response: Any) -> list[str]:
    return [v.strip() for v in response.headers.get("vary", "").split(",") if v.strip()]


# -- SRV-6: URL, then cookie, then Accept-Language, each validated -------------------------------


def test_SRV6_one_url_resolves_url_then_cookie_then_header_each_validated(session):
    """The spec's four requests on one URL, against a project serving en-us, it-it and es-es."""
    session(READ_KEY)
    with TestClient(locale_app()) as http:
        url = http.get("/page?locale=it-it", headers={"cookie": "langsys_locale=es-es", "accept-language": "es"})
        assert (url.json()["locale"], varies(url)) == ("it-it", [])

        cookie = http.get("/page", headers={"cookie": "langsys_locale=es-es", "accept-language": "it"})
        assert (cookie.json()["locale"], varies(cookie)) == ("es-es", ["Cookie"])

        header = http.get("/page", headers={"accept-language": "es"})
        assert header.json()["locale"] == "es-es" and "Accept-Language" in varies(header)

        unsupported = http.get("/page", headers={"cookie": "langsys_locale=fr-fr", "accept-language": "it"})
        assert unsupported.json()["locale"] == "it-it"
        assert "set-cookie" not in unsupported.headers  # never written back

        nothing = http.get("/page?locale=de-de")
        assert nothing.json()["locale"] == "en-us"  # an unsupported URL locale is skipped too
        assert set(varies(nothing)) == {"Cookie", "Accept-Language"}


def routed_app(**options: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware, **options)

    @app.get("/{segment}/page")
    def page(segment: str):
        return {"locale": get_current_locale().lower()}

    return app


def test_SRV6_a_path_segment_the_app_routes_by_is_the_url_step(session):
    session(READ_KEY)
    with TestClient(routed_app(path_segment=0)) as http:
        routed = http.get("/it-it/page", headers={"cookie": "langsys_locale=es-es", "accept-language": "es"})
        assert (routed.json()["locale"], varies(routed)) == ("it-it", [])

        unsupported = http.get("/fr-fr/page", headers={"cookie": "langsys_locale=es-es"})
        assert (unsupported.json()["locale"], varies(unsupported)) == ("es-es", ["Cookie"])


def test_SRV6_a_subdomain_the_app_routes_by_is_the_url_step(session):
    session(READ_KEY)
    with TestClient(locale_app(subdomain=True), base_url="http://it.site.test") as http:
        routed = http.get("/page", headers={"cookie": "langsys_locale=es-es", "accept-language": "es"})
    assert (routed.json()["locale"], varies(routed)) == ("it-it", [])


def test_SRV6_vary_is_merged_into_the_apps_own(session):
    session(READ_KEY)
    with TestClient(locale_app(vary="Origin")) as http:
        response = http.get("/page", headers={"accept-language": "es"})
    assert varies(response) == ["Origin", "Cookie", "Accept-Language"]
    assert len(response.headers.get_list("vary")) == 1


def test_SRV6_an_app_with_no_locale_cookie_does_not_vary_on_one(session):
    session(READ_KEY)
    with TestClient(locale_app(cookie_name=None)) as http:
        response = http.get("/page", headers={"cookie": "langsys_locale=it-it", "accept-language": "es"})
    assert (response.json()["locale"], varies(response)) == ("es-es", ["Accept-Language"])


# -- SRV-3's read-only half, with CONF-2's drift ----------------------------------------------------


def found_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware)

    @app.get("/found")
    def found(p: str):
        return {"text": t(p, "UI")}

    return app


def test_SRV3_a_session_that_may_not_write_pushes_nothing_even_once_the_world_would_accept(session, double):
    """An `ip_write` key not allow-listed for 127.0.0.1 learns it may not write. Then the world
    drifts — the allow-list widens, so the double would accept — and the state stays empty: the
    refused miss was never held for later. Control, in the drifted world: a request that learns it
    may write registers its own miss."""
    session(IP_WRITE_KEY, ip_allowlist=[])
    app = found_app()
    asyncio.run(drive(app, "/found", b"p=Refused"))
    assert double.phrases() == []

    double.seed(world(ip_allowlist=["127.0.0.1"]))
    get_client().flush_pending()
    assert double.phrases() == [], "a miss the server refused was held and sent once it could be"

    asyncio.run(drive(app, "/found", b"p=Control"))
    assert double.phrases() == [("UI", "Control")]


# -- MSG-8 through the handler --------------------------------------------------------------------


class Password(BaseModel):
    password: str = Field(title="password", min_length=12)


def test_MSG8_a_template_the_catalog_lacks_is_registered_after_the_failed_response(session, double):
    session(WRITE_KEY)
    app = FastAPI()
    app.add_middleware(LangsysMiddleware)
    install(app)

    @app.post("/signup")
    def signup(body: Password):
        return {}

    with TestClient(app) as http:
        assert http.post("/signup", json={"password": "short"}).status_code == 422
    assert double.phrases() == [
        ("Errors", "The password must be at least {min} characters."),
        ("Errors", "The request failed validation."),
    ]
