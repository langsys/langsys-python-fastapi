"""MSG-1..4, MSG-7 and MSG-9 — Pydantic's validation errors, translatable in its own words.

A real FastAPI app with this package's handler installed, compared request for request with the
same app answering with FastAPI's default handler: the entries asserted are what the app answers,
and FastAPI's own body must come back unchanged.
"""

from __future__ import annotations

import io
import json
import re
from datetime import date
from pathlib import Path
from typing import Any, List, Literal, Optional

import pytest
from fastapi import FastAPI, Query
from fastapi.testclient import TestClient
from langsys.cache import MemoryCache
from langsys.messages import fill_template, run_listing, template_markers
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from pydantic_core import PydanticCustomError

from langsys_fastapi import LangsysMiddleware, configure, get_client
from langsys_fastapi.messages import declared_templates, declares, entries_from_errors, install

API = "https://api.test/api"
AUTH = f"{API}/authorize-project/proj-1"
TRANS = re.compile(r"https://api\.test/api/translations")


class Item(BaseModel):
    label: str = Field(max_length=5)


class Signup(BaseModel):
    model_config = ConfigDict(extra="forbid")
    password: str = Field(min_length=12)
    initial: str = Field(min_length=1)
    age: int = Field(ge=18, lt=120)
    born: date = Field(ge=date(1900, 1, 1))
    tags: List[str] = Field(default_factory=list, max_length=2)
    plan: Literal["free", "pro"] = "free"
    items: List[Item] = Field(default_factory=list)
    coupon: Optional[str] = None
    username: str = "guest"

    @field_validator("coupon")
    @classmethod
    def _expired(cls, value: str) -> str:
        raise ValueError("The coupon has expired.")

    @field_validator("username")
    @declares("The username {name} is taken.")
    @classmethod
    def _taken(cls, value: str) -> str:
        raise PydanticCustomError("username_taken", "The username {name} is taken.", {"name": value})


class Nickname(BaseModel):
    nickname: str

    @field_validator("nickname")
    @classmethod
    def _spoken_for(cls, value: str) -> str:
        raise PydanticCustomError("nickname_taken", "{name} is spoken for.", {"name": value})


BAD = {
    "password": "short",
    "initial": "",
    "age": 150,
    "born": "1800-01-01",
    "tags": ["a", "b", "c"],
    "plan": "gold",
    "items": [{"label": "toolong"}],
    "coupon": "X",
    "username": "bob",
    "extra": 1,
}

#: loc -> (code, template, params): Pydantic's own type and sentence, numbers as markers.
EXPECTED = {
    ("query", "page"): ("greater_than_equal", "Input should be greater than or equal to {ge}", {"ge": 1}),
    ("body", "password"): ("string_too_short", "String should have at least {min_length} characters", {"min_length": 12}),
    ("body", "initial"): ("string_too_short", "String should have at least {min_length} character", {"min_length": 1}),
    ("body", "age"): ("less_than", "Input should be less than {lt}", {"lt": 120}),
    ("body", "born"): ("greater_than_equal", "Input should be greater than or equal to {ge}", {"ge": "1900-01-01"}),
    ("body", "tags"): (
        "too_long",
        "List should have at most {max_length} items after validation, not {actual_length}",
        {"max_length": 2, "actual_length": 3},
    ),
    ("body", "plan"): ("literal_error", "Input should be 'free' or 'pro'", None),
    ("body", "items", 0, "label"): ("string_too_long", "String should have at most {max_length} characters", {"max_length": 5}),
    ("body", "coupon"): ("value_error", "Value error, The coupon has expired.", None),
    ("body", "username"): ("username_taken", "The username {name} is taken.", {"name": "bob"}),
    ("body", "extra"): ("extra_forbidden", "Extra inputs are not permitted", None),
}


def make_app(*models: Any, key: Optional[str] = None, installed: bool = True) -> FastAPI:
    app = FastAPI()
    app.add_middleware(LangsysMiddleware)
    if installed:
        install(app) if key is None else install(app, key=key)

    @app.post("/signup")
    def signup(body: Signup, page: int = Query(1, ge=1)):
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


def failed(app: FastAPI, path: str = "/signup?page=0", body: Any = BAD) -> dict[str, Any]:
    with TestClient(app) as http:
        response = http.post(path, json=body)
    assert response.status_code == 422, response.text
    return response.json()


def by_loc(body: dict[str, Any], key: str = "langsys_errors") -> dict[tuple, dict[str, Any]]:
    return {tuple(entry["field"]): entry for entry in body[key]}


# -- MSG-1: FastAPI's body, entries attached -------------------------------------------------------


def test_MSG1_fastapis_own_body_is_unchanged_and_the_entries_ride_beside_it(bound):
    native = failed(make_app(installed=False))
    body = failed(make_app())
    assert list(body) == ["detail", "langsys_errors"]
    assert body["detail"] == native["detail"]
    assert len(body["langsys_errors"]) == len(body["detail"])


def test_MSG1_the_key_the_entries_sit_under_is_configurable(bound):
    body = failed(make_app(key="translations"))
    assert list(body) == ["detail", "translations"]


# -- MSG-2, MSG-3, MSG-9: Pydantic's own code, path and sentence ---------------------------------------


def test_MSG2_code_field_and_message_are_pydantics_own(bound):
    body = failed(make_app())
    for entry, error in zip(body["langsys_errors"], body["detail"]):
        assert (entry["code"], entry["field"], entry["message"]) == (error["type"], error["loc"], error["msg"])


def test_MSG3_MSG9_each_template_is_pydantics_sentence_before_its_values_are_filled(bound):
    entries = by_loc(failed(make_app()))
    assert {loc: (e["code"], e["template"], e.get("params")) for loc, e in entries.items()} == EXPECTED


def test_MSG3_text_pydantic_writes_into_its_sentence_is_written_in_so_it_is_translated_whole(bound):
    entries = by_loc(failed(make_app()))
    # the plural suffix, a Literal's choices and a validator's own sentence are in the template
    assert entries[("body", "initial")]["template"] != entries[("body", "password")]["template"]
    assert "'free' or 'pro'" in entries[("body", "plan")]["template"]
    assert entries[("body", "coupon")]["template"] == "Value error, The coupon has expired."


def test_MSG4_numbers_are_params_and_the_filled_template_is_the_message(bound):
    for entry in failed(make_app())["langsys_errors"]:
        params = entry.get("params") or {}
        assert entry["message"] == fill_template(entry["template"], params)
        assert ("params" in entry) == bool(template_markers(entry["template"]))
        assert all(isinstance(v, (int, str)) and not isinstance(v, bool) for v in params.values())
    assert by_loc(failed(make_app()))[("body", "age")]["params"] == {"lt": 120}


def test_MSG9_a_custom_error_with_no_declared_template_registers_as_its_text(bound):
    entry = by_loc(failed(make_app(Nickname), "/extra/0", {"nickname": "ada"}))[("body", "nickname")]
    assert (entry["code"], entry["template"], "params" in entry) == ("nickname_taken", "ada is spoken for.", False)


# -- MSG-7: the listing ---------------------------------------------------------------------------


def listed(app: FastAPI) -> tuple[set[str], list[str]]:
    templates, problems = set(), []
    for item in declared_templates(app):
        if isinstance(item, dict):
            templates.add(item["template"])
        else:
            problems.append(str(item))
    return templates, problems


def test_MSG7_the_listing_covers_every_template_the_app_emits_ahead_of_time(bound):
    templates, _ = listed(make_app())
    emitted = {e["template"] for e in failed(make_app())["langsys_errors"]}
    runtime = {"Value error, The coupon has expired."}  # a validator's own text; reported instead
    assert emitted - runtime <= templates, (emitted - runtime) - templates


def test_MSG7_what_cannot_be_listed_is_reported_with_where_and_what_to_do():
    _, problems = listed(make_app())
    assert any("'_expired'" in p and "@declares" in p for p in problems)
    assert any("field 'born'" in p and "{error}" in p for p in problems)
    assert not any("'_taken'" in p for p in problems), "a declared validator is listed, not reported"


def test_MSG7_the_command_reports_what_it_cannot_list_and_fails_only_under_strict():
    """The core's listing command over this binding's provider, with Pydantic's own label
    placeholders — it has none."""
    runs = {}
    for strict in (False, True):
        out = io.StringIO()
        runs[strict] = run_listing(
            [lambda: declared_templates(make_app())], out=out, label_placeholders=(), strict=strict
        )
        assert "'_expired'" in out.getvalue()
    assert runs == {False: 0, True: 1}


# -- the shared vectors ------------------------------------------------------------------------------

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "server-message-vectors.json").read_text(encoding="utf-8"))


class Person(BaseModel):
    name: str = Field(min_length=3)
    email: str


def test_MSG1_MSG4_the_measured_pydantic_entries_in_the_shared_vectors_are_what_this_builds():
    canonical = [
        {k: v for k, v in e.items() if k not in ("framework", "source")}
        for e in VECTORS["canonical_entries"]
        if e["framework"].startswith("Pydantic")
    ]
    assert len(canonical) == 2, "control: the vector file carries the measured Pydantic entries"
    try:
        Person(name="ab")
    except ValidationError as failure:
        built = entries_from_errors(failure.errors())
    assert sorted(built, key=str) == sorted(canonical, key=str)
