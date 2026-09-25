# langsys-fastapi

FastAPI (and Starlette) integration for [Langsys](https://langsys.dev) — a **thin wrapper**
over the [`langsys`](https://github.com/langsys/langsys-python) Python SDK. It adds only the
FastAPI-idiomatic pieces (request-locale middleware, a `t()` helper, DI access) and
delegates all translation to the base SDK.

The phrase in your code is the lookup key **and** the base-language default. Untranslated
phrases render as the source phrase.

## Install

```bash
pip install langsys-fastapi
```

Requires Python 3.9+.

## Setup

```python
from fastapi import FastAPI
from langsys_fastapi import LangsysMiddleware, configure, at

configure(api_key="…", project_id="…", base_locale="en-US")   # or LANGSYS_* env vars

app = FastAPI()
app.add_middleware(LangsysMiddleware, supported=["en-US", "es-ES"])

@app.get("/save")
async def save():
    return {"label": await at("Save", "UI")}
```

## Translating

The base SDK is synchronous. In `async def` endpoints use `at()` (it runs the call in a
threadpool, so it never blocks the event loop); in synchronous `def` endpoints — which
FastAPI already runs in a threadpool — call `t()` directly.

```python
await at("Hello, {name}!", "Greetings", name="Sarah")   # async endpoints
t("Save", "UI")                                          # sync endpoints
```

`phrase` and `category` are the helpers' own argument names, so a placeholder with either
name cannot be passed to `t()` / `at()` as a keyword — `category=` is always taken as the
category. For those, call the base SDK directly:
`get_langsys().translate("Filed under {category}", category="UI", params={"category": "News"})`.

Or reach the full SDK via dependency injection:

```python
from fastapi import Depends
from langsys import LangsysClient
from langsys_fastapi import get_langsys, current_locale

@app.get("/countries")
def countries(langsys: LangsysClient = Depends(get_langsys), loc: str = Depends(current_locale)):
    return {"locale": loc, "countries": [c.__dict__ for c in langsys.countries()]}
```

## How the locale is resolved

`LangsysMiddleware` picks the request locale in order: `?locale=`, then the
`langsys_locale` cookie, then the `Accept-Language` header. Each candidate goes through the
base SDK's `detect_preferred_locale`, so `supported` constrains all three alike: an
unsupported `?locale=` or cookie value falls through to the next source instead of being
used. The chosen locale is exposed to translations for the request via a context variable,
so a single shared client is safe across concurrent requests.

## After the response

Phrases missing from the catalog are queued while a request runs, under the base SDK's
request scope: nothing a request queues can be sent — by the SDK's debounce timer or by
another request finishing first — until that request's response has been sent. Once the
final response body is out, the middleware ends the scope and hands the queue to the SDK's
`flush_pending()`, and **the SDK decides** what happens to it — this package never looks at
the key type or the write capability itself:

- a **write-enabled** session registers them;
- a session the server says is **not** write-enabled discards them — a read key registers
  nothing;
- if write capability **could not be determined** (the API was unreachable), the queue is
  kept for the next attempt rather than lost.

The middleware also resets the SDK's observed write decision at the end of every request, so
one request's answer never carries into the next. If a handler raises, its scope ends as the
exception leaves the middleware and the SDK's debounce sends what it found shortly after, so
the error response goes out first.

For work done outside a request (startup code, background jobs), `get_langsys().flush_pending()`
is the manual flush. The automatic flush at process exit is best-effort: it does not run if
the process is killed.

## Configuration

`configure(...)` (call once at startup) or the environment:

| Option | Environment variable | |
|---|---|---|
| `api_key` | `LANGSYS_API_KEY` | required |
| `project_id` | `LANGSYS_PROJECT_ID` | required |
| `api_url` | `LANGSYS_API_URL` | API base — point it at a test double or a local stack |
| `base_locale` | `LANGSYS_BASE_LOCALE` | |
| `cache_ttl` | `LANGSYS_CACHE_TTL` | |
| `cache`, `timeout` | — | |

Every option is the base SDK's own, passed through unchanged. Calling `configure()` again
rebuilds the client — flushing the old client's queue first — so a later `api_url` takes
effect even after the first translation.

Middleware options only say where in a request the locale is read from: `query_param`
(default `locale`), `cookie_name` (default `langsys_locale`) and `supported`.

If you install your own client with `set_client()`, build it with
`locale_source=langsys_fastapi.locale.ContextVarLocaleSource()` so it reads the request
locale, and `debounce=None` so it sends nothing before the response.

## Development

Developed against a local checkout of the base SDK, linked editable:

```bash
python3 -m venv .venv
.venv/bin/pip install -e ../langsys-python -e '.[dev]'
.venv/bin/pytest
```

Live tests (`pytest -m integration`) run against a local Langsys stack and skip unless it is
configured; see `tests/test_live.py` for the environment. Conformance to the Langsys SDK
behaviour spec is recorded in [`CONFORMANCE.md`](CONFORMANCE.md).

## Releasing

Built and published to [PyPI](https://pypi.org) manually. Bump the version in `pyproject.toml`,
update `CHANGELOG.md`, then:

```bash
python -m build
twine upload dist/*   # requires a PyPI token with upload access
```

## License

MIT
