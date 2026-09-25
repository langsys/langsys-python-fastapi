"""MSG-1..4, MSG-7, MSG-9 and MSG-10 — failed validation as server-message entries.

A real FastAPI app with this package's handler installed; the entries asserted are what the app
answers. Every template is checked against the core's own rules (`check_template`, `fill`), and
the listing runs through the core's own command (`run_listing`).
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, List, Literal

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from langsys.cache import MemoryCache
from langsys.messages import (
    MESSAGE_CODES,
    check_template,
    fill_template,
    resolve_server_messages,
    run_listing,
    template_markers,
)
from pydantic import BaseModel, EmailStr, Field, field_validator

from langsys_fastapi import LangsysMiddleware, configure, get_client
from langsys_fastapi.messages import declared_templates, declares, install, message_error

VECTORS = json.loads(
    (Path(__file__).parent / "fixtures" / "server-message-vectors.json").read_text(encoding="utf-8")
)
API = "https://api.test/api"
AUTH = f"{API}/authorize-project/proj-1"
TRANS = re.compile(r"https://api\.test/api/translations")


class Item(BaseModel):
    label: str = Field(title="item label", max_length=5)


class Signup(BaseModel):
    email: EmailStr = Field(title="email")
    password: str = Field(title="password", min_length=12)
    age: int = Field(title="age", ge=18)
    born: date = Field(title="birth date", ge=date(1900, 1, 1))
    tags: List[str] = Field(default_factory=list, title="tags", max_length=2)
    plan: Literal["free", "pro"] = Field("free", title="plan")
    items: List[Item] = Field(default_factory=list, title="items")
    username: str = Field("guest", title="username")

    @field_validator("username")
    @declares("The username has already been taken.")
    @classmethod
    def _taken(cls, value: str) -> str:
        if value == "taken":
            raise message_error("already_taken", "The username has already been taken.")
        return value


class Unlabelled(BaseModel):
    cc_number: str


class Coupon(BaseModel):
    coupon: str = Field(title="coupon")

    @field_validator("coupon")
    @classmethod
    def _expired(cls, value: str) -> str:
        raise ValueError("The coupon has expired.")


BAD = {
    "email": "nope",
    "password": "short",
    "age": 3,
    "born": "1800-01-01",
    "tags": ["a", "b", "c"],
    "plan": "gold",
    "items": [{"label": "toolong"}],
    "username": "taken",
}

EXPECTED = {
    "page": ("too_small", "The page must be at least {min}.", {"min": 1}),
    "email": ("invalid_format", "The email must be a valid email address.", None),
    "password": ("too_short", "The password must be at least {min} characters.", {"min": 12}),
    "age": ("too_small", "The age must be at least {min}.", {"min": 18}),
    "born": ("invalid_date", "The birth date must be on or after {date}.", {"date": "1900-01-01"}),
    "tags": ("too_many", "The tags must not have more than {max} items.", {"max": 2}),
    "plan": ("invalid_option", "The selected plan is invalid.", None),
    "items.0.label": ("too_long", "The item label must not be longer than {max} characters.", {"max": 5}),
    "username": ("already_taken", "The username has already been taken.", None),
}


def make_app(*models: Any) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware)
    install(app)

    @app.post("/signup")
    def signup(body: Signup, page: int = Query(1, title="page", ge=1)):
        return {}

    for index, model in enumerate(models):
        app.post(f"/extra/{index}")(_endpoint(model))
    return app


def _endpoint(model: Any) -> Any:
    def endpoint(body: Any) -> Any:
        return {}

    endpoint.__annotations__ = {"body": model}  # the class itself, not a string to resolve
    return endpoint


@pytest.fixture()
def bound(httpx_mock):
    project = {
        "id": "proj-1", "title": "T", "base_locale": "en-us", "target_locales": ["es-es"],
        "default_locales": {}, "key_type": "read", "write_enabled": False,
        "langsys_settings": {"translatable_items": {"batch_limit": 200}},
    }
    httpx_mock.add_response(url=AUTH, json={"status": True, "data": project}, is_reusable=True)
    httpx_mock.add_response(url=TRANS, json={"status": True, "data": {"Errors": {}}}, is_reusable=True)
    configure(api_key="k", project_id="proj-1", api_url=API, base_locale="en-US", cache=MemoryCache())
    yield get_client()
    get_client().clear_pending()
    configure()


def failed(http: TestClient, path: str = "/signup?page=0", body: Any = BAD) -> dict[str, Any]:
    response = http.post(path, json=body)
    assert response.status_code == 422, response.text
    return response.json()


def entries_by_field(body: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["field"]: entry for entry in body["error"]["errors"]}


def listing(app: FastAPI) -> tuple[int, str]:
    out = io.StringIO()
    code = run_listing([lambda: declared_templates(app)], out=out)
    return code, out.getvalue()


# -- MSG-9: from the rules that failed -----------------------------------------------------------


def test_MSG9_entries_are_built_from_the_failed_rules(bound):
    with TestClient(make_app()) as http:
        entries = entries_by_field(failed(http))
    assert {f: (e["code"], e["template"], e.get("params")) for f, e in entries.items()} == EXPECTED
    # Pydantic's own rendering ("String should have at least 12 characters") never reaches a
    # template: every sentence is the wording table's.
    assert not any("should" in e["message"] for e in entries.values())


def test_MSG9_the_canonical_reference_entry_is_what_a_failed_min_length_produces(bound):
    canonical = next(e for e in VECTORS["canonical_entries"] if e.get("code") == "too_short")
    with TestClient(make_app()) as http:
        assert entries_by_field(failed(http))["password"] == canonical


def test_MSG9_a_text_only_failure_becomes_invalid_with_its_own_text(bound):
    with TestClient(make_app(Coupon)) as http:
        entry = entries_by_field(failed(http, "/extra/0", {"coupon": "X"}))["coupon"]
    assert (entry["code"], entry["template"]) == ("invalid", "The coupon has expired.")


# -- MSG-1..4: the entry and its envelope ---------------------------------------------------------


def test_MSG1_the_default_envelope_resolves_through_the_core_as_the_reference_does(bound):
    with TestClient(make_app()) as http:
        body = failed(http)
    assert body["status"] is False
    assert (body["error"]["code"], body["error"]["template"]) == (
        "validation_failed", "The request failed validation.",
    )
    reference = next(v for v in VECTORS["resolve"] if v["id"] == "langsys-envelope-validation")
    carries_envelope = len(reference["expected"]) == len(reference["body"]["error"]["errors"]) + 1
    resolved = resolve_server_messages(body)
    assert len(resolved) == len(body["error"]["errors"]) + (1 if carries_envelope else 0)
    assert all(entry in resolved for entry in body["error"]["errors"])


def test_MSG1_MSG4_every_entry_has_the_canonical_shape_and_message_is_the_filled_template(bound):
    with TestClient(make_app()) as http:
        entries = failed(http)["error"]["errors"]
    for entry in entries:
        keys = [k for k in ("field", "code", "message", "template", "params") if k in entry]
        assert list(entry) == keys, entry
        assert entry["message"] == fill_template(entry["template"], entry.get("params") or {})
        assert ("params" in entry) == bool(template_markers(entry["template"]))
        numbers = [v for k, v in (entry.get("params") or {}).items() if k != "date"]
        assert all(isinstance(v, int) for v in numbers), entry


def test_MSG2_codes_come_from_the_vocabulary_and_size_codes_follow_the_field_type(bound):
    with TestClient(make_app()) as http:
        entries = entries_by_field(failed(http))
    assert {e["code"] for e in entries.values()} <= set(MESSAGE_CODES)
    assert (entries["password"]["code"], entries["age"]["code"], entries["tags"]["code"]) == (
        "too_short", "too_small", "too_many",
    )


def test_MSG3_labels_are_written_in_and_markers_hold_only_values(bound):
    with TestClient(make_app()) as http:
        entries = failed(http)["error"]["errors"]
    for entry in entries:
        check_template(entry["template"])  # the core's MSG-11 refusal: raises if a label is a marker
        assert set(template_markers(entry["template"])) <= {"min", "max", "value", "date"}


# -- MSG-10: the framework's label ----------------------------------------------------------------


def test_MSG10_the_declared_title_is_the_label_not_the_key(bound):
    with TestClient(make_app()) as http:
        entries = entries_by_field(failed(http))
    assert entries["items.0.label"]["template"].startswith("The item label ")
    assert entries["page"]["template"].startswith("The page ")


def test_MSG7_MSG10_a_validated_field_with_no_label_fails_the_listing_by_name():
    code, output = listing(make_app(Unlabelled))
    assert code == 1
    assert "field 'cc_number'" in output and "Field(title=...)" in output


# -- MSG-7: the listing ---------------------------------------------------------------------------


def test_MSG7_the_listing_covers_every_runtime_template_with_zero_problems(bound):
    code, output = listing(make_app())
    assert code == 0 and "0 problem(s)" in output, output
    listed = {line.split("\t")[0] for line in output.splitlines()}
    with TestClient(make_app()) as http:
        body = failed(http)
    emitted = {e["template"] for e in body["error"]["errors"]} | {body["error"]["template"]}
    assert emitted <= listed, emitted - listed


def test_MSG7_a_validator_that_declares_no_templates_fails_the_listing():
    code, output = listing(make_app(Coupon))
    assert code == 1 and "'_expired'" in output and "@declares" in output
