"""Request-locale ASGI middleware.

Resolves the locale per request (``?locale=`` -> ``langsys_locale`` cookie ->
``Accept-Language``), exposes it to translations for the duration of the request via the
context variable, and — with a write key and ``auto_flush`` on — registers phrases
discovered while handling the request afterwards (dropping the queue on a read key so a
long-running server never accumulates it).

Implemented as raw ASGI (not ``BaseHTTPMiddleware``) so the context variable set here
reliably propagates into the endpoint.
"""

from __future__ import annotations

import logging
from http.cookies import SimpleCookie
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs

from langsys import canonicalize_locale
from starlette.concurrency import run_in_threadpool

from .client import get_client
from .locale import reset_current_locale, set_current_locale

logger = logging.getLogger("langsys")


class LangsysMiddleware:
    def __init__(
        self,
        app: object,
        *,
        query_param: str = "locale",
        cookie_name: str = "langsys_locale",
        supported: Optional[Sequence[str]] = None,
        auto_flush: bool = True,
    ) -> None:
        self.app = app
        self.query_param = query_param
        self.cookie_name = cookie_name
        self.supported = list(supported) if supported else []
        self.auto_flush = auto_flush

    async def __call__(self, scope: dict[str, Any], receive: object, send: object) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)  # type: ignore[operator]
            return

        client = get_client()
        locale = self._resolve(scope, client)
        token = set_current_locale(locale) if locale else None
        try:
            await self.app(scope, receive, send)  # type: ignore[operator]
        finally:
            if token is not None:
                reset_current_locale(token)
        await self._handle_pending(client)

    def _resolve(self, scope: dict[str, Any], client: object) -> str:
        headers = {k.decode().lower(): v.decode() for k, v in scope.get("headers") or []}

        query = parse_qs(scope.get("query_string", b"").decode())
        explicit = query.get(self.query_param, [None])[0]
        if explicit:
            return canonicalize_locale(explicit)

        cookie_header = headers.get("cookie")
        if cookie_header:
            jar: SimpleCookie = SimpleCookie()
            jar.load(cookie_header)
            morsel = jar.get(self.cookie_name)
            if morsel and morsel.value:
                return canonicalize_locale(morsel.value)

        detected = client.detect_preferred_locale(  # type: ignore[attr-defined]
            headers.get("accept-language"), self.supported or None
        )
        return detected or ""

    async def _handle_pending(self, client: object) -> None:
        if not client.has_pending:  # type: ignore[attr-defined]
            return
        try:
            await run_in_threadpool(self._flush_or_clear, client)
        except Exception as exc:  # pragma: no cover - never break the response
            logger.warning("langsys: flushing pending registrations failed: %s", exc)

    def _flush_or_clear(self, client: object) -> None:
        # Register on write keys (when enabled); otherwise drop the queue so it doesn't
        # grow unbounded on a long-running read-key server.
        if self.auto_flush and client.can_write:  # type: ignore[attr-defined]
            client.flush_pending()  # type: ignore[attr-defined]
        else:
            client.clear_pending()  # type: ignore[attr-defined]
