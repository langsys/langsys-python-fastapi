"""Live evidence against a real Langsys stack: the rows whose property depends on what the
API answers.

Skipped unless the environment below is set; run with ``pytest -m integration``. The
fixture is seeded on demand by langsys2's committed ``database/seeders/SdkIntegrationSeeder.php``
(slot 15, added in ``f8e499d1``), which ``php artisan db:seed`` runs outside production,
after ``OrganizationsTableSeeder``. Every id and raw key below is a fixed constant and the seeder
upserts, so the fixture — and this run — can be recreated exactly::

    LANGSYS_API_URL=http://langsys2.test/api
    LANGSYS_PROJECT_ID=c0de0000-5d10-4000-8000-000000000015
    LANGSYS_API_KEY=sdk_integration_fastapi_local_only_do_not_deploy
    LANGSYS_READ_KEY=sdk_integration_fastapi_read_local_only_do_not_deploy

What is asserted is what the server answered, recorded from its responses rather than from
anything the SDK sent. Registration asserts HTTP acceptance of the POST: the local stack
runs with its queue workers down, so an accepted item is enqueued and never reaches a
catalog a second read could observe.
"""

from __future__ import annotations

import asyncio
import os
import uuid

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from langsys import LangsysClient
from langsys.cache import MemoryCache
from test_request_boundary import BODY, drive, queued

from langsys_fastapi import LangsysMiddleware, at, configure, get_client, get_langsys, t

pytestmark = pytest.mark.integration

REQUIRED = ("LANGSYS_API_URL", "LANGSYS_PROJECT_ID", "LANGSYS_API_KEY", "LANGSYS_READ_KEY")
PHRASE, CATEGORY, TRANSLATION = "Technical Support", "CAT_3", "Soporte Técnico"


def live(key_env: str, answers: list) -> LangsysClient:
    missing = [name for name in REQUIRED if not os.environ.get(name)]
    if missing:
        pytest.skip("live stack not configured: " + ", ".join(missing))
    configure(
        api_key=os.environ[key_env],
        project_id=os.environ["LANGSYS_PROJECT_ID"],
        api_url=os.environ["LANGSYS_API_URL"],
        cache=MemoryCache(),
    )
    client = get_client()

    def answered(response):
        answers.append((response.request.method, response.request.url.path, response.status_code))

    # The server's answers, from its responses: never what the SDK tried to send.
    client._http._client.event_hooks["response"].append(answered)
    return client


@pytest.fixture(autouse=True)
def _unconfigure():
    yield
    configure()


def app_for(control: str) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware)

    @app.get("/sync")
    def sync_route():
        return {"text": t(PHRASE, CATEGORY), "control": t(control, CATEGORY), "queued": queued(get_client())}

    @app.get("/async")
    async def async_route():
        text, missed = await at(PHRASE, CATEGORY), await at(control, CATEGORY)
        return {"text": text, "control": missed, "queued": queued(get_client())}

    @app.get("/di")
    def di_route(langsys: LangsysClient = Depends(get_langsys)):
        text = langsys.translate(PHRASE, category=CATEGORY)
        missed = langsys.translate(control, category=CATEGORY)
        return {"text": text, "control": missed, "queued": queued(langsys)}

    @app.get("/found")
    def found():
        return {"text": t(control, CATEGORY)}

    return app


@pytest.mark.parametrize("path", ["/sync", "/async", "/di"])
def test_LIVE_SRV1_the_served_bytes_carry_the_request_locale(path):
    """On the read key, so the control miss is discarded at the end of the request rather
    than registered, and stays a miss on every run."""
    answers: list = []
    live("LANGSYS_READ_KEY", answers)
    control = "FastAPI SRV-1 control, never registered"
    with TestClient(app_for(control)) as http:
        body = http.get(path, params={"locale": "es-ES"}).json()
    assert body == {"text": TRANSLATION, "control": control, "queued": [control]}
    assert [a for a in answers if a[0] == "POST"] == []


@pytest.mark.parametrize(
    ("key_env", "registrations"),
    [("LANGSYS_READ_KEY", 0), ("LANGSYS_API_KEY", 1)],
    ids=["read-only-key-pushes-nothing", "CONTROL-write-key-on-the-same-render-pushes"],
)
def test_LIVE_SRV3_REG3_accepted_after_the_response_and_never_from_a_read_key(key_env, registrations):
    """A fresh phrase per run: the stack keeps what it accepts, so a phrase an earlier run
    registered could stop being a miss."""
    events: list = []
    client = live(key_env, events)
    control = f"FastAPI SRV-3 {uuid.uuid4().hex}"
    asyncio.run(drive(app_for(control), "/found", b"locale=es-ES", events))

    accepted = [e for e in events if e[:2] == ("POST", "/api/translatable-items")]
    assert len(accepted) == registrations, events
    assert all(200 <= status < 300 for _, _, status in accepted), accepted
    if accepted:
        assert events.index(accepted[0]) > events.index(BODY), events
    assert queued(client) == []
