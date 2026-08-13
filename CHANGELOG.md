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
