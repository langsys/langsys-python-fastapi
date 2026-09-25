# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- FastAPI/Starlette integration over the `langsys` base SDK: ASGI middleware that resolves the
  request locale from the query string, a cookie or `Accept-Language` — each matched against
  `supported` by the SDK's own matcher — a synchronous `t()` helper plus an async `at()` that
  runs the blocking SDK call in a threadpool, and dependency-injection access to the client
  and the current locale (`get_langsys`, `current_locale`).
- A request-safe shared client whose locale comes from a `contextvars` context variable, so one
  instance serves concurrent requests, each in its own language.
- Registration after the response: phrases a request discovers are held under the SDK's
  request scope until its response has been sent, then handed to the SDK's `flush_pending()`,
  which registers, keeps or discards them as the server decides. The observed write decision
  is reset at the end of every request.
- `configure()` rebuilds the client, flushing the previous client's queue first, so a later
  `api_url` takes effect even after the first translation.
- `CONFORMANCE.md`, grading every rule of the Langsys SDK behaviour spec against this package,
  with the live, request-boundary and absence-probe tests behind it.
