import asyncio
import re

import pytest
from langsys import LangsysClient
from langsys.cache import MemoryCache

from langsys_fastapi import t
from langsys_fastapi.client import reset_client, set_client
from langsys_fastapi.locale import (
    ContextVarLocaleSource,
    get_current_locale,
    reset_current_locale,
    set_current_locale,
)
from langsys_fastapi.middleware import LangsysMiddleware

TRANS = re.compile(r"https://api\.test/api/translations")
AUTH = re.compile(r"https://api\.test/api/authorize-project")


def catalog(data):
    return {"status": True, "words": 0, "untranslatedWords": 0, "data": data}


def authorize(key_type="read"):
    return {
        "status": True,
        "data": {
            "id": "proj-1",
            "title": "T",
            "base_locale": "en-us",
            "target_locales": ["es-es"],
            "default_locales": {},
            "key_type": key_type,
            "langsys_settings": {"translatable_items": {"batch_limit": 200}},
        },
    }


@pytest.fixture()
def client():
    reset_client()
    instance = LangsysClient(
        "k",
        "proj-1",
        api_url="https://api.test/api",
        base_locale="en-US",
        cache=MemoryCache(),
        locale_source=ContextVarLocaleSource(),
    )
    set_client(instance)
    yield instance
    reset_client()


def _scope(path="/", query=b"", headers=None):
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "query_string": query,
        "headers": headers or [],
    }


async def _drive(mw, scope):
    """Run the middleware over a scope with a trivial inner app; capture the locale
    visible inside the endpoint."""
    seen = {}

    async def receive():
        return {"type": "http.request", "body": b""}

    sent = []

    async def send(message):
        sent.append(message)

    async def inner(s, r, sd):
        seen["locale"] = get_current_locale()
        await sd({"type": "http.response.start", "status": 200, "headers": []})
        await sd({"type": "http.response.body", "body": b"ok"})

    mw.app = inner
    await mw(scope, receive, send)
    return seen


def test_t_helper_uses_request_locale(httpx_mock, client):
    httpx_mock.add_response(url=TRANS, json=catalog({"UI": {"Save": "Guardar"}}))
    token = set_current_locale("es-ES")
    try:
        assert t("Save", "UI") == "Guardar"
    finally:
        reset_current_locale(token)


def test_middleware_locale_from_query(httpx_mock, client):
    httpx_mock.add_response(url=AUTH, json=authorize(), is_reusable=True)
    seen = asyncio.run(_drive(LangsysMiddleware(None), _scope(query=b"locale=es-es")))
    assert seen["locale"].lower() == "es-es"
    assert get_current_locale() == ""  # reset after the request


def test_middleware_locale_from_accept_language(httpx_mock, client):
    httpx_mock.add_response(url=AUTH, json=authorize(), is_reusable=True)
    headers = [(b"accept-language", b"es-ES,en;q=0.5")]
    seen = asyncio.run(_drive(LangsysMiddleware(None), _scope(headers=headers)))
    assert seen["locale"].lower() == "es-es"


def test_middleware_locale_from_cookie(httpx_mock, client):
    httpx_mock.add_response(url=AUTH, json=authorize(), is_reusable=True)
    headers = [(b"cookie", b"langsys_locale=es-ES")]
    seen = asyncio.run(_drive(LangsysMiddleware(None), _scope(headers=headers)))
    assert seen["locale"].lower() == "es-es"


def test_middleware_clears_pending_on_read_key(httpx_mock, client):
    httpx_mock.add_response(url=AUTH, json=authorize("read"), is_reusable=True)
    httpx_mock.add_response(url=TRANS, json=catalog({"UI": {}}))

    mw = LangsysMiddleware(None)

    async def inner(s, r, sd):
        t("A brand new phrase", "UI")  # missing -> queued for discovery
        await sd({"type": "http.response.start", "status": 200, "headers": []})
        await sd({"type": "http.response.body", "body": b"ok"})

    async def run():
        mw.app = inner

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(_):
            return None

        await mw(_scope(query=b"locale=es-ES"), receive, send)

    asyncio.run(run())
    assert client.has_pending is False  # read key -> queue dropped
