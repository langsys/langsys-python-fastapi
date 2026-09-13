# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Initial FastAPI/Starlette integration over the `langsys` base SDK: request-locale ASGI
  middleware that resolves the language from the query string, a cookie, or `Accept-Language`,
  a synchronous `t()` helper plus an async `at()` that runs the (blocking) SDK call in a
  threadpool, and dependency-injection access to the client and the current locale
  (`get_langsys`, `current_locale`).
- A request-safe shared client whose locale comes from a `contextvars` context variable, so a
  single instance is safe under concurrent async traffic, each request in its own language.
- `CONFORMANCE.md`, grading every rule of the Langsys SDK behaviour spec against this package,
  with the live, request-boundary and absence-probe tests behind it.

### Changed

- The middleware no longer decides what happens to phrases a request discovered. Once the
  response has been sent it hands the queue to the base SDK's `flush_pending()`, which
  registers, keeps or discards it. It previously checked write capability itself and cleared
  the queue whenever that check was not a plain yes — including when capability could not be
  determined, so a network blip lost everything queued.
- **Removed the middleware's `auto_flush` option.** It shared a name with the base SDK's
  `auto_flush` (flush at process exit), but turning it off here discarded the queue at the end
  of every request.
- `supported` now constrains `?locale=` and the locale cookie, not only `Accept-Language`.

### Fixed

- The observed write decision is reset at the end of every request, so one request's answer
  can no longer silence registration in the next.
- `configure()` and `reset_client()` flush the retired client's queue before closing it.
- A request header containing a non-UTF-8 byte no longer fails the request.
