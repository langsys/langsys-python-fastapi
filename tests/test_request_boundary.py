"""The request boundary — the behaviour this binding adds, which the core cannot see.

The end-of-request flush, its place after the response, and the per-request reset of the
write decision. Each test names the rule it proves, and every "sends nothing" is paired
with a control proving the same setup does send when it should. Counts are of requests
the test double actually received and answered.
"""

from __future__ import annotations

import asyncio
import json
import re
import threading
import time
from typing import Any, Optional

import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from langsys import LangsysClient
from langsys.cache import MemoryCache

from langsys_fastapi import LangsysMiddleware, at, configure, get_client, get_langsys, t
from langsys_fastapi.locale import get_current_locale, reset_current_locale, set_current_locale

API = "https://api.test/api"
AUTH = f"{API}/authorize-project/proj-1"
ITEMS = f"{API}/translatable-items"
TRANS = re.compile(r"https://api\.test/api/translations")
CONTROL = "Not in any catalog"
START, BODY = ("sent", "http.response.start"), ("sent", "http.response.body")


def auth(key_type: str = "write", write_enabled: Any = True) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "proj-1",
        "title": "T",
        "base_locale": "en-us",
        "target_locales": ["es-es", "de-de"],
        "default_locales": {},
        "key_type": key_type,
        "langsys_settings": {"translatable_items": {"batch_limit": 200}},
    }
    if write_enabled is not None:
        data["write_enabled"] = write_enabled
    return {"status": True, "data": data}


def envelope(data: Any = None, write_enabled: Any = None) -> dict[str, Any]:
    body: dict[str, Any] = {"status": True, "words": 0, "untranslatedWords": 0}
    body["data"] = {"UI": {}} if data is None else data
    if write_enabled is not None:
        body["write_enabled"] = write_enabled
    return body


def by_locale(request: httpx.Request) -> httpx.Response:
    url = str(request.url).lower()
    for locale, text in (("es-es", "Precios"), ("de-de", "Preise")):
        if locale in url:
            return httpx.Response(200, json=envelope({"UI": {"Pricing": text}}))
    return httpx.Response(200, json=envelope({"UI": {}}))


def posts(httpx_mock: Any) -> list[httpx.Request]:
    return [r for r in httpx_mock.get_requests() if r.method == "POST"]


def queued(client: LangsysClient) -> list[str]:
    return [p["phrase"] for p in client.pending_phrases]


def record_registrations(httpx_mock: Any, events: list, key_type="write", write_enabled=True):
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth(key_type, write_enabled), is_reusable=True)

    def accept(request: httpx.Request) -> httpx.Response:
        events.append(("registered", str(request.url)))
        return httpx.Response(200, json={"status": True})

    httpx_mock.add_callback(accept, url=ITEMS, is_reusable=True, is_optional=True)


@pytest.fixture()
def bound(httpx_mock):
    configure(api_key="k", project_id="proj-1", api_url=API, base_locale="en-US", cache=MemoryCache())
    client = get_client()
    yield client
    client.clear_pending()  # teardown must not send on the test's behalf
    configure()


def make_app(**options: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware, **options)
    gate: dict[str, Any] = {"arrived": 0}
    app.state.gate = gate
    barrier = threading.Barrier(2, timeout=5)

    @app.get("/found")
    def found(n: int = 1, sleep: float = 0.0):
        texts = [t(f"Phrase {i}", "UI") for i in range(n)]
        time.sleep(sleep)
        return {"texts": texts}

    @app.get("/srv1/sync")
    def srv1_sync():
        return {"text": t("Pricing", "UI"), "control": t(CONTROL, "UI"), "queued": queued(get_client())}

    @app.get("/srv1/async")
    async def srv1_async():
        text, control = await at("Pricing", "UI"), await at(CONTROL, "UI")
        return {"text": text, "control": control, "queued": queued(get_client())}

    @app.get("/srv1/di")
    def srv1_di(langsys: LangsysClient = Depends(get_langsys)):
        text = langsys.translate("Pricing", category="UI")
        control = langsys.translate(CONTROL, category="UI")
        return {"text": text, "control": control, "queued": queued(langsys)}

    @app.get("/srv2/async")
    async def srv2_async():
        event = gate.setdefault("event", asyncio.Event())
        gate["arrived"] += 1
        if gate["arrived"] == 2:
            event.set()
        await event.wait()
        return {"text": await at("Pricing", "UI")}

    @app.get("/srv2/sync")
    def srv2_sync():
        barrier.wait()
        return {"text": t("Pricing", "UI")}

    @app.get("/raises")
    def raises():
        t("Phrase raised", "UI")
        raise RuntimeError("handler failed")

    @app.get("/held")
    async def held(p: str):
        await at(p, "UI")
        gate.setdefault("recorded", asyncio.Event()).set()
        await gate.setdefault("release", asyncio.Event()).wait()
        return {}

    @app.get("/quick")
    async def quick(p: str):
        text = await at(p, "UI")
        await gate.setdefault("recorded", asyncio.Event()).wait()
        return {"text": text}

    return app


async def drive(
    app: FastAPI, path: str, query: bytes = b"", events: Optional[list] = None, label: str = "sent"
) -> Any:
    """One raw ASGI request, recording every message the app sends, in order."""
    events = [] if events is None else events
    body = bytearray()
    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "root_path": "",
        "query_string": query,
        "headers": [(b"host", b"testserver")],
        "server": ("testserver", 80),
        "client": ("127.0.0.1", 50000),
    }

    async def receive():
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message):
        events.append((label, message["type"]))
        if message["type"] == "http.response.body":
            body.extend(message.get("body", b""))

    await app(scope, receive, send)
    return json.loads(bytes(body) or b"null")


# -- BIND-2 / GATE-2: the lane decision is the core's --------------------------


def test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware(httpx_mock, bound):
    """The defect measured at 29bb650. The middleware branched on `can_write`, which
    collapses *unknown* to False, then called `clear_pending()`: an empty queue and 0
    POSTs, where the core on its own holds with `capability-unknown`."""
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_exception(httpx.ConnectError("blip"), url=AUTH, is_reusable=True)
    with TestClient(make_app()) as http:
        assert http.get("/found").status_code == 200
    assert queued(bound) == ["Phrase 0"], "the binding discarded a queue the core holds"
    assert posts(httpx_mock) == []


def test_GATE2_CONTROL_a_server_no_still_discards_through_the_middleware(httpx_mock, bound):
    """Holding is not "never discard": a queue the server has just refused is dropped."""
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth("read", False), is_reusable=True)
    with TestClient(make_app()) as http:
        http.get("/found")
    assert queued(bound) == [] and posts(httpx_mock) == []


def test_REG3_CONTROL_a_write_enabled_request_registers_what_it_found(httpx_mock, bound):
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth("write", True), is_reusable=True)
    httpx_mock.add_response(url=ITEMS, json={"status": True}, is_reusable=True)
    with TestClient(make_app()) as http:
        http.get("/found")
    assert len(posts(httpx_mock)) == 1 and queued(bound) == []


# -- GATE-3: the decision does not survive the request -------------------------


def test_GATE3_a_no_observed_in_one_request_does_not_silence_the_next(httpx_mock, bound):
    """One request is told no; the next carries no fresh answer — warm authorize, cached
    catalog, the hot path. Held past the boundary, that stale no outranks the plain write
    key's fallback and the second request silently registers nothing: GATE-3's "one
    anonymous request first makes the allow-listed origin register nothing"."""
    httpx_mock.add_response(url=AUTH, json=auth("write", write_enabled=None), is_reusable=True)
    answers = iter([False])
    httpx_mock.add_callback(
        lambda request: httpx.Response(200, json=envelope(write_enabled=next(answers, None))),
        url=TRANS,
        is_reusable=True,
    )
    httpx_mock.add_response(url=ITEMS, json={"status": True}, is_reusable=True, is_optional=True)
    bound.authorize()  # startup: warm metadata, as an app validating its key would

    with TestClient(make_app()) as http:
        http.get("/found?locale=es-ES")
        assert posts(httpx_mock) == [] and queued(bound) == [], "control: the no held in its own request"
        http.get("/found?locale=es-ES")

    assert len(posts(httpx_mock)) == 1, "a decision observed by the previous request silenced this one"
    assert queued(bound) == []


# -- SRV-3 / REG-3: after the response, and never from a read-only key ---------


def test_SRV3_REG3_registration_happens_after_the_response_is_sent(httpx_mock, bound):
    events: list = []
    record_registrations(httpx_mock, events)
    asyncio.run(drive(make_app(), "/found", events=events))
    assert events == [START, BODY, ("registered", ITEMS)]


def test_SRV3_a_slow_handler_sends_nothing_before_its_response(httpx_mock, bound):
    """The core's debounce timer (400ms) fires while this handler is still running; the miss
    it recorded is held by the request scope until the response has been sent."""
    events: list = []
    record_registrations(httpx_mock, events)
    asyncio.run(drive(make_app(), "/found", query=b"sleep=0.8", events=events))
    assert events == [START, BODY, ("registered", ITEMS)]


@pytest.mark.parametrize(
    ("key_type", "write_enabled", "registrations"),
    [("read", False, 0), ("write", True, 1)],
    ids=["read-only-key-pushes-nothing", "CONTROL-write-key-on-the-same-render-pushes"],
)
def test_SRV3_a_read_only_key_pushes_nothing_and_a_write_key_on_the_same_render_does(
    httpx_mock, bound, key_type, write_enabled, registrations
):
    events: list = []
    record_registrations(httpx_mock, events, key_type, write_enabled)
    asyncio.run(drive(make_app(), "/found", events=events))
    assert [e for e in events if e[0] == "registered"] == [("registered", ITEMS)] * registrations
    assert queued(bound) == []


def test_SRV3_another_request_s_flush_sends_nothing_before_this_response(httpx_mock, bound):
    """A quick request's end-of-request flush sends only what its own scope released: a
    concurrent request's miss waits for that request's response. Ordered by events, not sleeps: the quick request waits
    until the held one has recorded its miss, and the held one is released only once the
    quick one has been flushed."""
    events: list = []
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth("write", True), is_reusable=True)

    def accept(request: httpx.Request) -> httpx.Response:
        items = json.loads(request.content)["translatable_items"]
        events.append(("registered", sorted(item["phrase"] for item in items)))
        return httpx.Response(200, json={"status": True})

    httpx_mock.add_callback(accept, url=ITEMS, is_reusable=True)
    app = make_app()

    async def quick_then_release():
        await drive(app, "/quick", b"p=Quick", events, label="quick")
        app.state.gate.setdefault("release", asyncio.Event()).set()

    async def scenario():
        await asyncio.gather(
            drive(app, "/held", b"p=Held", events, label="held"), quick_then_release()
        )

    asyncio.run(scenario())
    held_start = events.index(("held", "http.response.start"))
    sent_held = [i for i, e in enumerate(events) if e[0] == "registered" and "Held" in e[1]]
    assert sent_held and min(sent_held) > held_start, events


def test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response(httpx_mock, bound):
    """A request whose handler raised gets no flush of its own — one would run before
    Starlette's error middleware sends the 500. Its scope ends as the exception leaves the
    middleware, and the core's debounce sends the miss after the error response."""
    events: list = []
    record_registrations(httpx_mock, events)
    app = make_app()

    async def run():
        with pytest.raises(RuntimeError):
            await drive(app, "/raises", events=events)

    asyncio.run(run())
    deadline = time.monotonic() + 3
    while ("registered", ITEMS) not in events and time.monotonic() < deadline:
        time.sleep(0.05)
    assert events == [START, BODY, ("registered", ITEMS)]


# -- REG-2 / REG-3 -------------------------------------------------------------


def test_REG2_everything_one_request_found_goes_out_as_one_request(httpx_mock, bound):
    """A burst from one render becomes one request, with no flush written by the app."""
    record_registrations(httpx_mock, [])
    with TestClient(make_app()) as http:
        http.get("/found?n=5")
    sent = posts(httpx_mock)
    assert len(sent) == 1
    assert len(json.loads(sent[0].content)["translatable_items"]) == 5
    assert queued(bound) == []


def test_REG3_reconfiguring_hands_the_retired_client_s_queue_to_the_core_first(httpx_mock, bound):
    httpx_mock.add_response(url=TRANS, json=envelope(), is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth("write", True), is_reusable=True)
    httpx_mock.add_response(url=ITEMS, json={"status": True}, is_reusable=True)
    token = set_current_locale("es-ES")
    try:
        t("Found at startup", "UI")
    finally:
        reset_current_locale(token)
    assert queued(bound) == ["Found at startup"]

    configure(api_key="k", project_id="proj-1", api_url=API, base_locale="en-US", cache=MemoryCache())

    assert len(posts(httpx_mock)) == 1, "the retired client's queue was closed away unsent"
    assert queued(bound) == []


# -- SRV-1 / SRV-2: what is served, and whose catalog --------------------------


@pytest.mark.parametrize("path", ["/srv1/sync", "/srv1/async", "/srv1/di"])
def test_SRV1_the_served_bytes_carry_the_request_locale(httpx_mock, bound, path):
    """Asserted on the response body, on every route this binding exposes: `t()` in a sync
    endpoint, `at()` in an async one, and the core client through DI. The absent control
    in the same render emits the base language and is queued as a miss — what separates
    "translated" from "rendered a catalog that happened to be complete"."""
    httpx_mock.add_callback(by_locale, url=TRANS, is_reusable=True)
    httpx_mock.add_response(url=AUTH, json=auth("read", False), is_reusable=True, is_optional=True)
    with TestClient(make_app()) as http:
        body = http.get(path, params={"locale": "es-ES"}).json()
    assert body == {"text": "Precios", "control": CONTROL, "queued": [CONTROL]}


@pytest.mark.parametrize("path", ["/srv2/async", "/srv2/sync"])
def test_SRV2_concurrent_requests_in_different_locales_see_only_their_own(httpx_mock, bound, path):
    """Both requests are inside their scope — both locales set — before either translates.
    Run one after the other this proves nothing; the failure is the interleave."""
    httpx_mock.add_callback(by_locale, url=TRANS, is_reusable=True)
    app = make_app()

    async def both():
        return await asyncio.gather(
            drive(app, path, b"locale=es-ES"), drive(app, path, b"locale=de-DE")
        )

    assert asyncio.run(both()) == [{"text": "Precios"}, {"text": "Preise"}]


# -- BIND-1: delete the binding and call the core directly ---------------------

VECTORS = [
    ("Pricing", "UI", {}),
    (CONTROL, "UI", {}),
    ("Hello, {name}!", "UI", {"name": "Sarah"}),
    ("{count, plural, one {# item} other {# items}}", "UI", {"count": 3}),
    ("{count, plural, one {# item} other {# items}}", "UI", {"count": None}),
    ("Save", None, {}),
]


def test_BIND1_deleting_the_binding_changes_nothing_but_shape(httpx_mock, bound):
    """The spec's first heuristic, executed: the same vectors through `t()`, through `at()`
    and straight through the core give the same text and queue the same misses."""
    httpx_mock.add_callback(by_locale, url=TRANS, is_reusable=True)
    direct = LangsysClient(
        "k", "proj-1", api_url=API, base_locale="en-US", cache=MemoryCache(),
        auto_flush=False, debounce=None,
    )
    try:
        for phrase, category, params in VECTORS:
            token = set_current_locale("es-ES")
            try:
                via_t = t(phrase, category, **params)
                via_at = asyncio.run(at(phrase, category, **params))
            finally:
                reset_current_locale(token)
            core = direct.translate(phrase, category=category, params=params or None, locale="es-ES")
            assert via_t == via_at == core, phrase
        assert bound.pending_phrases == direct.pending_phrases
    finally:
        direct.clear_pending()
        direct.close()


# -- the middleware's own request parsing --------------------------------------


def locale_app(**options: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware, **options)

    @app.get("/locale")
    def current():
        return {"locale": get_current_locale()}

    return app


def test_supported_constrains_an_explicit_locale_as_it_constrains_accept_language(bound):
    """Found while writing CONFORMANCE.md: only Accept-Language was matched against
    `supported`, so any `?locale=` or cookie value reached the API as a locale — a catalog
    fetch and a cache entry per distinct string a visitor cares to send."""
    with TestClient(locale_app(supported=["en-US", "es-ES"])) as http:
        unsupported = http.get("/locale?locale=de-DE", headers={"accept-language": "es"})
        assert unsupported.json() == {"locale": "es-ES"}
        assert http.get("/locale?locale=es", headers={"accept-language": "en"}).json() == {"locale": "es-ES"}
        assert http.get("/locale", headers={"cookie": "langsys_locale=fr-FR"}).json() == {"locale": ""}


def test_a_non_utf8_header_byte_does_not_fail_the_request(bound):
    """Headers were decoded as UTF-8; HTTP header bytes are latin-1, and one stray byte in
    any header raised before the app ran."""
    with TestClient(locale_app()) as http:
        response = http.get("/locale?locale=es-ES", headers={"x-legacy": b"caf\xe9"})
    assert response.json() == {"locale": "es-ES"}
