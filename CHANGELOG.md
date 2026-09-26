# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project adheres to
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- FastAPI/Starlette integration over the `langsys` base SDK: ASGI middleware that serves each
  request in the locale the SDK resolves — the URL's `?locale=`, then the locale cookie, then
  `Accept-Language`, each validated against the project's locales — with the `Vary` headers that
  choice depended on; a synchronous `t()` helper plus an async `at()` that runs the blocking SDK
  call in a threadpool; and dependency-injection access to the client and the current locale
  (`get_langsys`, `current_locale`).
- Validation errors made translatable without changing them:
  `langsys_fastapi.messages.install(app)` keeps FastAPI's own 422 body and attaches an entry per
  error under a configurable key (`langsys_errors` by default) — Pydantic's error type as `code`, its `loc` as `field`, and its
  own sentence as `template` with `params` filling its markers; `@declares` names a custom
  validator's templates; and `declared_templates(app)` is a provider for the SDK's listing
  command.
- `configure(snapshot=…)` seeds the client from an exported catalog snapshot at startup.
- A locale an app resolves itself and sets on `request.state.locale` is served as it resolved it.
- `configure()` rebuilds the client, flushing the previous client's queue first, so a later
  `api_url` takes effect even after the first translation.
- `CONFORMANCE.md`, grading every rule of the Langsys SDK behaviour spec against this package,
  with the live, request-boundary and absence-probe tests behind it.
