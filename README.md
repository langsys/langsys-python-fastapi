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
`langsys_locale` cookie, then the `Accept-Language` header (matched against `supported`).
It exposes that locale to translations for the request via a context variable, so a single
shared client is safe across concurrent requests. With a **write** key and `auto_flush`
(default on), phrases discovered while handling the request are registered afterwards; with
a **read** key nothing is written.

## Configuration

`configure(...)` (call once at startup) or the `LANGSYS_*` environment variables:
`api_key` / `project_id` (required), `api_url`, `base_locale`, `cache`, `cache_ttl`,
`timeout`. Middleware options: `query_param`, `cookie_name`, `supported`, `auto_flush`.

## Releasing

Built and published to [PyPI](https://pypi.org) manually. Bump the version in `pyproject.toml`,
update `CHANGELOG.md`, then:

```bash
python -m build
twine upload dist/*   # requires a PyPI token with upload access
```

## License

MIT
