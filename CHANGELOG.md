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
- Validation errors as translatable server messages: `langsys_fastapi.messages.install(app)`
  answers a failed request with entries built from the Pydantic rules that failed, each a whole
  sentence with the field's `title` written in; `message_error()` and `@declares` for custom
  validators; and `declared_templates(app)`, a provider for the SDK's listing command.
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
