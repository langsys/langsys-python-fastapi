"""Artifact inspection: the evidence behind every `delegated` row, and behind BIND-2..6.

A probe that reads no code reports absence for everything, so every probe asserts it read
the package, and carries a firing control — a snippet the same filter must match, taken
from the defect it guards against where there was one. Probes read code only: comments and
docstrings are blanked first, so prose that *names* a mechanism (this package's docstrings
name several) is not mistaken for the mechanism.
"""

from __future__ import annotations

import ast
import inspect
import io
import re
import tokenize
from pathlib import Path
from types import SimpleNamespace

import langsys
import pytest
from langsys import LangsysClient
from langsys.cache import MemoryCache

import langsys_fastapi
from langsys_fastapi import LangsysMiddleware, configure, get_client, get_langsys, t
from langsys_fastapi.locale import reset_current_locale, set_current_locale

SRC = Path(langsys_fastapi.__file__).resolve().parent
README = Path(__file__).resolve().parents[1] / "README.md"


def code_only(source: str) -> str:
    """``source`` with docstrings and comments blanked; line numbers preserved."""
    lines = source.splitlines(keepends=True)
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            first = node.body[0] if node.body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                for n in range(first.lineno - 1, first.end_lineno or first.lineno):
                    lines[n] = "\n"
    text = "".join(lines)
    lines = text.splitlines(keepends=True)
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        if token.type == tokenize.COMMENT:
            row, col = token.start
            lines[row - 1] = lines[row - 1][:col] + "\n"
    return "".join(lines)


def package_code() -> list[str]:
    files = sorted(SRC.rglob("*.py"))
    assert len(files) >= 5, f"the probe read {len(files)} files: any absence would be vacuous"
    return [code_only(f.read_text(encoding="utf-8")) for f in files]


def count(pattern: str, sources: list[str]) -> int:
    return sum(len(re.findall(pattern, s)) for s in sources)


#: The 29bb650 end-of-request branch, verbatim: the firing control for the capability probes.
DEFECT_29BB650 = """
if self.auto_flush and client.can_write:
    client.flush_pending()
else:
    client.clear_pending()
"""
CAPABILITY = r"write_enabled|key_type|KeyType|can_write|_resolve_write_enabled|_observed_decision"
CATALOG = r"get_translations|catalog|UNCATEGORIZED"
REPORT = r"hint|discovery"
ICU = r"interpolate|plural|MessageFormat|babel"
CID = r"custom_id|md5|hashlib|legacy"
TOK = r"lxml|tokeniz|translatable_attributes|translate_page|translate_content_block|\bre\."
MARK = r"data-ls|data-langsys|contentblock|resolved"
MIGRATION = r"gettext|ngettext|msgid|legacy_key|\.po\b|legacy"

#: rule -> (pattern that must not occur in this package's code, firing control)
PROBES: dict[str, tuple[str, str]] = {
    "GATE-1": (r"key_type|KeyType", 'if client.key_type == "write":\n    pass\n'),
    "GATE-2": (r"can_write|clear_pending|_resolve_write_enabled", DEFECT_29BB650),
    "GATE-4": (r"cache\.set\(|write_enabled", 'cache.set(key, payload["data"])\n'),
    "GATE-5": (r"registered_items|mark_registered|_registered\b", "self._registered.add(key)\n"),
    "GATE-6": (REPORT, 'http.post("discovery/hint", json={"url": url})\n'),
    "GATE-7": (REPORT + r"|register_phrases|register_content_blocks", "client.register_phrases([p])\n"),
    "GATE-8": (CAPABILITY, 'flag = data.get("write_enabled")\n'),
    "CAT-1": (CATALOG, "entry = catalog[category].get(phrase)\n"),
    "CAT-2": (CATALOG, "text = catalog[category][phrase] or phrase\n"),
    "CAT-3": (CATALOG + r"|isinstance\(\w+, dict\)", "known = isinstance(value, dict)\n"),
    "REG-1": (r"translatable-items|register_phrases|register_content_blocks|\.post\(", 'http.post("translatable-items", json=batch)\n'),
    "REG-2": (
        r"\bdebounce\b|Timer\(|_schedule_flush|call_later|create_task",
        "self._timer = threading.Timer(delay, self._debounced_flush)\n",
    ),
    "REG-6": (r"\b_pending\b|_pending_blocks|clear_pending|snapshot", "self._pending.clear()\n"),
    "REG-7": (r"_sending|in_flight|Semaphore", "if not self._sending.acquire(blocking=False):\n    pass\n"),
    "REG-8": (r"backoff|retry|\bsleep\(", "time.sleep(self._backoff_seconds)\n"),
    "REG-9": (r"batch_limit|chunk", 'limit = settings["batch_limit"]\n'),
    "REG-10": (r"[\"']success[\"']|[\"']skipped[\"']", 'result = {"success": True}\n'),
    "REG-11": (r"ellipsis|\\u2026|…|endswith\(", 'if phrase.endswith("..."):\n    pass\n'),
    "REG-12": (r"isinstance\(\w+, dict\)|\{32\}", "if isinstance(value, dict):\n    pass\n"),
    "HINT-2": (REPORT, 'http.post("discovery/hint", json={"url": url})\n'),
    "ICU-1": (ICU, "text = interpolate(text, params, locale)\n"),
    "ICU-2": (ICU, "text = interpolate(text, {k: v for k, v in params.items()}, locale)\n"),
    "ICU-3": (ICU, 'text = text.replace("#", "{" + plural_arg + "}")\n'),
    "ICU-4": (ICU, 'logger.debug("recovered plural argument %s", name)\n'),
    "ICU-5": (ICU, "from babel import plural\n"),
    "CID-1": (CID, "cid = hashlib.md5(payload).hexdigest()\n"),
    "CID-2": (CID, 'custom_id = generate(category or "", tokens)\n'),
    "CID-3": (CID, "ids = legacy_custom_ids(category, tokens)\n"),
    "CID-4": (CID, "if catalog_block == content:\n    custom_id = legacy\n"),
    "TOK-1": (TOK, 'root = lxml.html.fromstring(html)\n'),
    "TOK-2": (TOK, 'words = re.split(r"\\s+", text)\n'),
    "TOK-3": (TOK, "attrs = list(translatable_attributes)\n"),
    "TOK-4": (TOK, 'value = re.sub(r"\\s+", " ", value)\n'),
    "TOK-5": (TOK, 'text = re.sub(r"%(\\w+)%", r"{\\1}", text)\n'),
    "MARK-1": (MARK, 'host.set("data-ls-contentblock", cid)\n'),
    "MARK-2": (MARK, 'cid = host.get("data-langsys-contentblock")\n'),
    "CACHE-1": (r"cache\.(get|set)\(|cache_key|[\"']auth_|[\"']translations_", 'self._cache.set(f"translations_{locale}", catalog)\n'),
    "OBS-1": (r"write-enabled|_warned_unusable|_notice_unusable", 'logger.warning("this session is not write-enabled")\n'),
    "WIRE-1": (r"Authorization|X-Write-Grant|Bearer", 'headers = {"X-Authorization": key}\n'),
    "WIRE-2": (r"status_code|\b204\b|\.json\(\)", "if response.status_code == 204:\n    pass\n"),
    "WIRE-3": (r"__uncategorized__|locale\w*\.lower\(\)|normalize_locale", "wire = locale.lower()\n"),
    "WIRE-4": (r"\bauthorize\(|get_translations\(|\brefresh\(|httpx|urlopen", "project = client.authorize()\n"),
    "GATE-9": (r"discovery_base_locale_only|base_locale_only", 'gate = data.get("discovery_base_locale_only")\n'),
    "CACHE-2": (r"_failed_until|failure_window|negative_cache", "self._failed_until[key] = now + delay\n"),
    "REG-13": (r"_catalog_loaded|first_read|settled", "if not self._catalog_loaded:\n    pass\n"),
    "ICU-6": (ICU + r"|formatter", "formatter = MessageFormatter(locale)\n"),
    "MARK-3": (MARK, 'host.set("data-ls-resolved", locale)\n'),
    "MARK-4": (MARK, 'cid = host.get("data-langsys-contentblock")\n'),
    "TOK-6": (TOK, 'text = re.sub(r"\\s+", " ", text)\n'),
    **{f"MIG-{n}": (MIGRATION, "text = gettext(key)\n") for n in range(1, 10)},
    "SNAP-1": (r"snapshot|export_catalog", "snapshot = export_catalog(categories)\n"),
    "SNAP-3": (r"snapshot|export_catalog", "catalog = load_snapshot(path)\n"),
    "MSG-5": (r"render_server_message|\.render\(", "text = client.render_server_message(entry)\n"),
    "MSG-6": (r"DEFAULT_MESSAGE_CATEGORY|[\"']Errors[\"']", 'category = "Errors"\n'),
    "MSG-8": (r"_queue_missing|register_templates", "client.register_templates(listing)\n"),
    "MSG-11": (
        r"LABEL_MARKERS|check_template|warn_translatable_marker_value|_FRAMEWORK_PLACEHOLDERS",
        "check_template(template)\n",
    ),
    "BIND-2": (CAPABILITY, DEFECT_29BB650),
    # `debounce` included: setting the core's debounce schedules sends from this layer.
    "BIND-3": (
        r"httpx|urllib\.request|urlopen|\brequests\b|Timer\(|\bsleep\(|retry|backoff|atexit"
        r"|\bdebounce\b|\bX-[A-Z]",
        "_client = LangsysClient(locale_source=ContextVarLocaleSource(), debounce=None, **_config)\n",
    ),
    "BIND-5": (
        r"lru_cache|functools\.cache\b|memoi|WeakValueDictionary|_results\b|_translations\b",
        "@functools.lru_cache(maxsize=None)\ndef t(phrase):\n    pass\n",
    ),
}


def test_PROBE_the_filter_blanks_prose_and_keeps_code():
    source = '"""write_enabled in a docstring"""\nx = 1  # write_enabled in a comment\ny = "write_enabled"\n'
    assert count("write_enabled", [code_only(source)]) == 1


@pytest.mark.parametrize("rule", sorted(PROBES))
def test_ABSENCE(rule):
    pattern, control = PROBES[rule]
    assert count(pattern, [code_only(control)]) >= 1, "firing control did not fire"
    assert count(pattern, package_code()) == 0


# -- BIND-4: no configuration the core does not define --------------------------

CLIENT_OPTIONS = set(inspect.signature(LangsysClient.__init__).parameters) - {"self"}
#: Where in an HTTP request the app keeps the locale — SRV-6's wiring, which BIND-4 allows.
#: The core has no request, so it cannot define these, and none decides what the product does.
REQUEST_SHAPE = {"app", "query_param", "cookie_name"}


def introduced_by_configure(fn) -> set:
    return set(inspect.signature(fn).parameters) - CLIENT_OPTIONS


def introduced_by_middleware(fn) -> set:
    params = set(inspect.signature(fn).parameters) - {"self"}
    # A client option on the middleware is a second, differently scoped meaning for a name
    # the core already defines: 29bb650's `auto_flush` meant "discard the queue" here and
    # "flush at process exit" in the core.
    return (params & CLIENT_OPTIONS) | (params - REQUEST_SHAPE)


def test_BIND4_the_middleware_introduces_only_request_shape_options():
    def at_29bb650(self, app, *, query_param="locale", cookie_name="c", supported=None, auto_flush=True): ...

    assert introduced_by_middleware(at_29bb650) == {"auto_flush", "supported"}, "firing control"
    assert introduced_by_middleware(LangsysMiddleware.__init__) == set()


def test_BIND4_configure_introduces_no_option_the_core_does_not_define():
    def with_discovery(*, api_key=None, discovery=True): ...

    assert introduced_by_configure(with_discovery) == {"discovery"}, "firing control"
    assert introduced_by_configure(configure) == set()


# -- BIND-6: the narrowest surface ----------------------------------------------


def shadowed(namespace) -> set:
    """Exported names the core also exports, bound here to something else."""
    return {
        name
        for name in namespace.__all__
        if hasattr(langsys, name) and getattr(langsys, name) is not getattr(namespace, name)
    }


def test_BIND6_nothing_exported_shadows_a_core_name_with_something_else():
    fake = SimpleNamespace(__all__=["canonicalize_locale"], canonicalize_locale=lambda v: v)
    assert shadowed(fake) == {"canonicalize_locale"}, "firing control"
    assert shadowed(langsys_fastapi) == set()


def test_BIND6_DI_hands_out_the_core_client_itself():
    configure(api_key="k", project_id="proj-1", api_url="https://api.test/api", cache=MemoryCache())
    try:
        client = get_langsys()
        assert type(client) is LangsysClient and client is get_client()
    finally:
        configure()


# -- WIRE-5: redirectable, and findable ------------------------------------------


def test_WIRE5_configure_redirects_the_api_base_even_after_first_use(httpx_mock):
    """Proven by where requests arrive, not by the setter existing — and redirected after
    the client was built and used, the ordering the rule names as the silent failure."""
    httpx_mock.add_response(
        url=re.compile(r"https://(first|second)\.test/api/translations"),
        json={"status": True, "data": {"UI": {"Save": "Guardar"}}},
        is_reusable=True,
    )
    token = set_current_locale("es-ES")
    try:
        configure(api_key="k", project_id="proj-1", api_url="https://first.test/api", cache=MemoryCache())
        assert t("Save", "UI") == "Guardar"
        configure(api_key="k", project_id="proj-1", api_url="https://second.test/api", cache=MemoryCache())
        assert t("Save", "UI") == "Guardar"
    finally:
        reset_current_locale(token)
        configure()
    assert [r.url.host for r in httpx_mock.get_requests()] == ["first.test", "second.test"]


def readme_section(heading: str) -> str:
    text = README.read_text(encoding="utf-8")
    start = text.index(heading)
    end = text.find("\n## ", start + 1)
    return text[start : end if end != -1 else None]


def findable(section: str) -> bool:
    return "api_url" in section and "LANGSYS_API_URL" in section


def test_WIRE5_the_seam_is_findable_where_an_integrator_looks():
    assert not findable("## Configuration\n`api_key`, `project_id`."), "firing control"
    assert findable(readme_section("## Configuration"))
    assert "api_url" in (configure.__doc__ or "")
