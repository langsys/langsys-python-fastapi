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
app.add_middleware(LangsysMiddleware)

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

If your app resolves the locale itself, set it on `request.state.locale` in a middleware that
runs before `LangsysMiddleware` (add it after `LangsysMiddleware`, since Starlette runs the
last-added middleware first). That locale is served — mapped to the project's form, a bare `es`
to the project's default Spanish, an unsupported one as the base locale — and nothing else is
consulted.

Otherwise `LangsysMiddleware` asks the base SDK which locale to serve, in order: the URL — the path
segment, subdomain or `?locale=` your app routes by — then the `langsys_locale` cookie, then `Accept-Language`, and otherwise the project's base locale.
Every candidate is checked against the locales the project serves — its base and target
locales — and an unsupported one is skipped. The middleware never writes the cookie; your app
owns it.

The response carries the `Vary` headers the choice depended on — `Cookie`, `Accept-Language`, or
neither when the URL decided — merged into any `Vary` your app sets, so a cache in front of the
site keys on them. The chosen locale is exposed to translations through a context variable, so a
single shared client is safe across concurrent requests.

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

## Validation errors

`install(app)` makes FastAPI's validation errors translatable without changing them. FastAPI still
answers a failed request with its own 422 body; each error also gets an entry beside it, under
`langsys_errors`:

```python
from langsys_fastapi.messages import install

install(app)   # or install(app, key="translations")
```

```json
{"detail": [{"type": "string_too_short", "loc": ["body", "password"],
             "msg": "String should have at least 12 characters", "input": "short",
             "ctx": {"min_length": 12}}],
 "langsys_errors": [{"template": "String should have at least {min_length} characters",
                     "params": {"min_length": 12},
                     "message": "String should have at least 12 characters",
                     "field": ["body", "password"], "code": "string_too_short"}]}
```

An entry's `code` is Pydantic's error `type` and its `field` Pydantic's `loc`, unchanged.
`template` is Pydantic's own sentence before its values are filled — the phrase a translator
sees — and `params` fill its markers; `message` is Pydantic's own `msg`. A client renders the
entry through the SDK and falls back to `message`.

A custom validator raises Pydantic's `PydanticCustomError` as usual. Naming its templates with
`@declares` lets the listing below register them ahead of time:

```python
from pydantic import BaseModel, field_validator
from pydantic_core import PydanticCustomError
from langsys_fastapi.messages import declares

class Signup(BaseModel):
    username: str

    @field_validator("username")
    @declares("The username {name} is taken.")
    @classmethod
    def available(cls, value: str) -> str:
        if taken(value):
            raise PydanticCustomError("username_taken", "The username {name} is taken.", {"name": value})
        return value
```

A validator that raises a plain `ValueError` produces Pydantic's `Value error, …` sentence, with
its text written in.

To register templates before any user sees one, list them with the base SDK's command and a
provider over your app:

```python
# myapp/langsys.py
from langsys_fastapi.messages import declared_templates
from myapp.main import app

def templates():
    return declared_templates(app)
```

```bash
python -m langsys.messages --provider myapp.langsys:templates              # list
python -m langsys.messages --provider myapp.langsys:templates --register   # and register them
```

The command also reports what it cannot list ahead of time — a sentence Pydantic fills with its
parser's own text, a validator that declares no templates — each with where it is. Those register
the first time they are emitted, after the response. Add `--strict` to make any such report fail
the command, for a team that wants no error ever shown untranslated.

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
| `message_category` | — | category validation templates are registered under; default `Errors` |
| `snapshot` | — | an exported catalog snapshot — a path, its JSON or a `Snapshot` — the client is seeded with when it is built: lookups it holds need no network |

Every option is the base SDK's own, passed through unchanged. Calling `configure()` again
rebuilds the client — flushing the old client's queue first — so a later `api_url` takes
effect even after the first translation.

Middleware options only say where in a request your app keeps the locale:

| Option | Default | |
|---|---|---|
| `path_segment` | `None` | index of the path segment holding the locale — `0` for `/es/pricing` |
| `subdomain` | `False` | the host's first label holds the locale — `es.example.com` |
| `query_param` | `locale` | query parameter holding the locale |
| `cookie_name` | `langsys_locale` | cookie holding the locale; `None` when the app keeps none, so no response varies on one |
| `state_key` | `locale` | the `request.state` attribute an app that resolves the locale itself sets |

The URL's locale is the first of `path_segment`, `subdomain` and `query_param` present.

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

The contract tests start the fleet's shared API double (`tests/contract-fixture/`), which needs
Node 18 or later. Live tests (`pytest -m integration`) run against a local Langsys stack and skip unless it is
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
