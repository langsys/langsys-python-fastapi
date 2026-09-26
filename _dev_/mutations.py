#!/usr/bin/env python3
"""CONF-3 — prove each rule this binding implements by breaking it.

    python3 _dev_/mutations.py

For every mutation: apply it to the source, run the unit suite, and require that each
**named** test fails — not merely that something does. The source is restored after each
one whatever happens, and the tree is checked byte-for-byte against its starting state at
the end. The unmutated suite must be green first, or no mutation result means anything.
Exits non-zero if a mutation does not apply or does not redden every test it names.

`delegated` rows are not mutated here: their evidence is an absence probe, and each probe's
firing control (tests/test_probes.py) is the mutation — the code the probe must catch.
"""

from __future__ import annotations

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PKG = "src/langsys_fastapi"
BOUNDARY = "tests/test_request_boundary.py"
PROBES = "tests/test_probes.py"
CONTRACT = "tests/test_contract.py"
MESSAGES = "tests/test_messages.py"


@dataclass
class Mutation:
    rule: str
    what: str
    path: str
    swaps: list[tuple[str, str]]
    reddens: list[str] = field(default_factory=list)


MUTATIONS = [
    Mutation(
        "BIND-2",
        "restore the 29bb650 capability branch at the end of the request",
        f"{PKG}/middleware.py",
        [(
            "            await run_in_threadpool(client.flush_pending)\n",
            "            await run_in_threadpool(\n"
            "                client.flush_pending if client.can_write else client.clear_pending\n"
            "            )\n",
        )],
        [
            f"{BOUNDARY}::test_BIND2_GATE2_an_unknown_capability_holds_the_queue_through_the_middleware",
            f"{PROBES}::test_ABSENCE[BIND-2]",
            f"{PROBES}::test_ABSENCE[GATE-2]",
        ],
    ),
    Mutation(
        "GATE-3",
        "drop the per-request reset of the write decision",
        f"{PKG}/middleware.py",
        [("                client.reset_write_decision()\n", "                pass\n")],
        [f"{BOUNDARY}::test_GATE3_a_no_observed_in_one_request_does_not_silence_the_next"],
    ),
    Mutation(
        "REG-3",
        "drop the end-of-request flush",
        f"{PKG}/middleware.py",
        [(
            "                if completed:\n                    await self._flush(client)\n",
            "                if completed:\n                    pass\n",
        )],
        [
            f"{BOUNDARY}::test_REG3_CONTROL_a_write_enabled_request_registers_what_it_found",
            f"{BOUNDARY}::test_SRV3_REG3_registration_happens_after_the_response_is_sent",
            f"{BOUNDARY}::test_SRV3_a_read_only_key_pushes_nothing_and_a_write_key_on_the_same_render_does"
            "[CONTROL-write-key-on-the-same-render-pushes]",
        ],
    ),
    Mutation(
        "REG-3",
        "close the retired client without flushing it",
        f"{PKG}/client.py",
        [("        client.flush_pending()\n", "        pass\n")],
        [f"{BOUNDARY}::test_REG3_reconfiguring_hands_the_retired_client_s_queue_to_the_core_first"],
    ),
    Mutation(
        "SRV-3",
        "release and flush before the final body is sent",
        f"{PKG}/middleware.py",
        [(
            "            await send(message)\n"
            '            if message["type"] == "http.response.body"'
            ' and not message.get("more_body"):\n'
            "                client.end_request_scope(held)\n",
            '            if message["type"] == "http.response.body"'
            ' and not message.get("more_body"):\n'
            "                client.end_request_scope(held)\n"
            "                await self._flush(client)\n"
            "            await send(message)\n",
        )],
        [f"{BOUNDARY}::test_SRV3_REG3_registration_happens_after_the_response_is_sent"],
    ),
    Mutation(
        "SRV-3",
        "never open the request scope",
        f"{PKG}/middleware.py",
        [(
            "        held = client.begin_request_scope()\n",
            '        held = __import__("langsys").RequestScope()\n',
        )],
        [
            f"{BOUNDARY}::test_SRV3_a_slow_handler_sends_nothing_before_its_response",
            f"{BOUNDARY}::test_SRV3_another_request_s_flush_sends_nothing_before_this_response",
        ],
    ),
    Mutation(
        "SRV-3",
        "leave a raised request's scope open",
        f"{PKG}/middleware.py",
        [("            client.end_request_scope(held)\n            try:\n", "            try:\n")],
        [f"{BOUNDARY}::test_SRV3_a_request_that_raised_releases_its_misses_after_the_error_response"],
    ),
    Mutation(
        "SRV-1",
        "never expose the resolved locale to the request",
        f"{PKG}/middleware.py",
        [(
            "        token = set_current_locale(choice.locale) if choice.locale else None\n",
            "        token = None\n",
        )],
        [
            f"{BOUNDARY}::test_SRV1_the_served_bytes_carry_the_request_locale[/srv1/sync]",
            f"{BOUNDARY}::test_SRV1_the_served_bytes_carry_the_request_locale[/srv1/async]",
            f"{BOUNDARY}::test_SRV1_the_served_bytes_carry_the_request_locale[/srv1/di]",
        ],
    ),
    Mutation(
        "SRV-2",
        "hold the request locale in a process global instead of the context variable",
        f"{PKG}/locale.py",
        [
            (
                "def set_current_locale(locale: str) -> contextvars.Token[str]:\n"
                "    return _current_locale.set(locale)\n",
                '_LAST = [""]\n\n\n'
                "def set_current_locale(locale: str) -> contextvars.Token[str]:\n"
                "    _LAST[0] = locale\n"
                "    return _current_locale.set(locale)\n",
            ),
            (
                "    def get(self) -> str:\n        return _current_locale.get()\n",
                "    def get(self) -> str:\n        return _LAST[0]\n",
            ),
        ],
        [
            f"{BOUNDARY}::test_SRV2_concurrent_requests_in_different_locales_see_only_their_own[/srv2/async]",
            f"{BOUNDARY}::test_SRV2_concurrent_requests_in_different_locales_see_only_their_own[/srv2/sync]",
        ],
    ),
    Mutation(
        "BIND-1",
        "t() drops the category on its way to the core",
        f"{PKG}/client.py",
        [(
            "get_client().translate(phrase, category=category, params=params or None)",
            "get_client().translate(phrase, category=None, params=params or None)",
        )],
        [f"{BOUNDARY}::test_BIND1_deleting_the_binding_changes_nothing_but_shape"],
    ),
    Mutation(
        "BIND-3",
        "build the shared client with debounce=None",
        f"{PKG}/client.py",
        [(
            "LangsysClient(locale_source=ContextVarLocaleSource(), **_config)",
            "LangsysClient(locale_source=ContextVarLocaleSource(), debounce=None, **_config)",
        )],
        [f"{PROBES}::test_ABSENCE[BIND-3]", f"{PROBES}::test_ABSENCE[REG-2]"],
    ),
    Mutation(
        "BIND-4",
        "give the middleware the 29bb650 auto_flush option back",
        f"{PKG}/middleware.py",
        [(
            '        state_key: Optional[str] = "locale",\n    ) -> None:\n',
            '        state_key: Optional[str] = "locale",\n'
            "        auto_flush: bool = True,\n    ) -> None:\n",
        )],
        [f"{PROBES}::test_BIND4_the_middleware_introduces_only_request_shape_options"],
    ),
    Mutation(
        "BIND-5",
        "memoize t()",
        f"{PKG}/client.py",
        [
            ("import threading\n", "import functools\nimport threading\n"),
            (
                "def t(phrase: str, category: Optional[str] = None, **params: Any) -> str:\n",
                "@functools.lru_cache(maxsize=None)\n"
                "def t(phrase: str, category: Optional[str] = None, **params: Any) -> str:\n",
            ),
        ],
        [f"{PROBES}::test_ABSENCE[BIND-5]"],
    ),
    Mutation(
        "BIND-6",
        "export a core name bound to a reimplementation",
        f"{PKG}/__init__.py",
        [(
            "__all__ = [\n",
            "def canonicalize_locale(value: str) -> str:\n    return value\n\n\n"
            '__all__ = [\n    "canonicalize_locale",\n',
        )],
        [f"{PROBES}::test_BIND6_nothing_exported_shadows_a_core_name_with_something_else"],
    ),
    Mutation(
        "WIRE-5",
        "configure() no longer rebuilds the client",
        f"{PKG}/client.py",
        [("    reset_client()\n", "    pass\n")],
        [f"{PROBES}::test_WIRE5_configure_redirects_the_api_base_even_after_first_use"],
    ),
    Mutation(
        "SRV-6",
        "never send the Vary the locale choice depended on",
        f"{PKG}/middleware.py",
        [(
            '            if message["type"] == "http.response.start" and choice.vary:\n',
            "            if False:\n",
        )],
        [
            f"{CONTRACT}::test_SRV6_one_url_resolves_url_then_cookie_then_header_each_validated",
            f"{CONTRACT}::test_SRV6_vary_is_merged_into_the_apps_own",
            f"{CONTRACT}::test_SRV6_an_app_with_no_locale_cookie_does_not_vary_on_one",
        ],
    ),
    Mutation(
        "SRV-6",
        "replace the app's own Vary instead of merging into it",
        f"{PKG}/middleware.py",
        [(
            "    named.extend(v for v in vary if v.lower() not in lowered)\n",
            "    named = list(vary)\n",
        )],
        [f"{CONTRACT}::test_SRV6_vary_is_merged_into_the_apps_own"],
    ),
    Mutation(
        "SRV-6",
        "ignore the path segment the app routes by",
        f"{PKG}/middleware.py",
        [("        if self.path_segment is not None:\n", "        if False:\n")],
        [f"{CONTRACT}::test_SRV6_a_path_segment_the_app_routes_by_is_the_url_step"],
    ),
    Mutation(
        "SRV-6",
        "ignore the subdomain the app routes by",
        f"{PKG}/middleware.py",
        [("        if self.subdomain:\n", "        if False:\n")],
        [f"{CONTRACT}::test_SRV6_a_subdomain_the_app_routes_by_is_the_url_step"],
    ),
    Mutation(
        "SRV-6",
        "ignore the locale the app resolved itself",
        f"{PKG}/middleware.py",
        [(
            "            framework=app_locale if isinstance(app_locale, str) "
            "and app_locale else None,\n",
            "            framework=None,\n",
        )],
        [
            f"{CONTRACT}::test_SRV6_a_locale_the_app_resolved_is_served_whatever_else_the_request_says"
            "[mapped-to-project-form]",
        ],
    ),
    Mutation(
        "SRV-6",
        "never offer the cookie as a candidate",
        f"{PKG}/middleware.py",
        [("            cookie=cookie,\n", "            cookie=None,\n")],
        [f"{CONTRACT}::test_SRV6_one_url_resolves_url_then_cookie_then_header_each_validated"],
    ),
    Mutation(
        "MSG-1",
        "replace FastAPI's own 422 body with the entries alone",
        f"{PKG}/messages.py",
        [(
            "        attach_server_messages(body, entries, key)\n",
            "        body = {key: entries}\n",
        )],
        [f"{MESSAGES}::test_MSG1_fastapis_own_body_is_unchanged_and_the_entries_ride_beside_it"],
    ),
    Mutation(
        "MSG-2",
        "map Pydantic's error type onto a code of ours",
        f"{PKG}/messages.py",
        [(
            '        code = str(error.get("type", ""))\n',
            '        code = "invalid"\n',
        )],
        [f"{MESSAGES}::test_MSG2_code_field_and_message_are_pydantics_own"],
    ),
    Mutation(
        "MSG-3",
        "write numbers into the sentence instead of leaving them markers",
        f"{PKG}/messages.py",
        [("        elif name in ctx and _is_value(ctx[name]):\n", "        elif False:\n")],
        [
            f"{MESSAGES}::test_MSG3_MSG9_each_template_is_pydantics_sentence_before_its_values_are_filled",
            f"{MESSAGES}::test_MSG4_numbers_are_params_and_the_filled_template_is_the_message",
        ],
    ),
    Mutation(
        "MSG-7",
        "ignore the templates a validator declares",
        f"{PKG}/messages.py",
        [("        if declared is not None:\n", "        if False:\n")],
        [f"{MESSAGES}::test_MSG7_what_cannot_be_listed_is_reported_with_where_and_what_to_do"],
    ),
    Mutation(
        "SNAP-2",
        "never seed the client from the configured snapshot",
        f"{PKG}/client.py",
        [("                if _snapshot is not None:\n", "                if False:\n")],
        [f"{BOUNDARY}::test_SNAP2_a_snapshot_given_to_configure_seeds_the_client_and_answers_with_no_network"],
    ),
]


def run_suite() -> tuple[int, set[str], str]:
    env = {k: v for k, v in os.environ.items() if not k.startswith("LANGSYS_")}
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-rfE"],
        cwd=ROOT, env=env, capture_output=True, text=True,
    )
    failed = set(re.findall(r"^(?:FAILED|ERROR) (\S+)", proc.stdout, re.M))
    summary = (proc.stdout.strip().splitlines() or ["(no output)"])[-1]
    return proc.returncode, failed, summary


def tree_digest() -> str:
    digest = hashlib.sha256()
    for path in sorted((ROOT / PKG).rglob("*.py")):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def main() -> int:
    start = tree_digest()
    code, failed, summary = run_suite()
    print(f"baseline: {summary}")
    if code != 0:
        print("ERROR - the unmutated suite is not green; no mutation result would mean anything")
        return 1

    ok = True
    for m in MUTATIONS:
        target = ROOT / m.path
        original = target.read_text(encoding="utf-8")
        try:
            mutated = original
            for old, new in m.swaps:
                if mutated.count(old) != 1:
                    raise LookupError(f"{old[:50]!r} occurs {mutated.count(old)} times")
                mutated = mutated.replace(old, new)
            target.write_text(mutated, encoding="utf-8")
            _, failed, summary = run_suite()
        except LookupError as exc:
            print(f"ERROR - {m.rule}: mutation did not apply: {exc}")
            ok = False
            continue
        finally:
            target.write_text(original, encoding="utf-8")
        missed = [name for name in m.reddens if name not in failed]
        verdict = "reddens" if not missed else "DOES NOT REDDEN"
        ok = ok and not missed
        named = f"{len(m.reddens) - len(missed)}/{len(m.reddens)} named"
        print(f"\n{m.rule}: {m.what}\n  {verdict} {named}; suite: {summary}")
        for name in m.reddens:
            print(f"    {'red ' if name in failed else 'GREEN'} {name.split('::', 1)[1]}")

    if tree_digest() != start:
        print("ERROR - the source tree was not restored")
        return 1
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
