"""Request-locale ASGI middleware — and the request boundary the core cannot see.

For each HTTP request it:

1. resolves the locale (``?locale=`` -> ``langsys_locale`` cookie -> ``Accept-Language``),
   matching each candidate through the core's ``detect_preferred_locale`` against
   ``supported``, and exposes it to translations via the request-scoped context variable;
2. opens the core's request scope, so nothing the request queues can be sent — by the
   core's debounce timer or by another request's flush — before its response is out. The
   scope ends once the final response body has been sent, and the middleware then hands
   the queue to the core's public ``flush_pending()``. Whether that registers, holds (the
   capability could not be determined) or discards (the server said no) is the core's
   decision, taken at its send site: this middleware never reads or branches on
   capability;
3. forgets the observed write decision with ``reset_write_decision()``, so it cannot
   outlive the request.

Raw ASGI rather than ``BaseHTTPMiddleware``, so the context variable set here reliably
propagates into the endpoint, and so "the app has returned" means the final response
message has been sent.
"""

from __future__ import annotations

import contextlib
import logging
from http.cookies import CookieError, SimpleCookie
from typing import Any, Optional, Sequence
from urllib.parse import parse_qs

from langsys import LangsysClient
from starlette.concurrency import run_in_threadpool

from .client import get_client
from .locale import reset_current_locale, set_current_locale

logger = logging.getLogger("langsys")


class LangsysMiddleware:
    def __init__(
        self,
        app: Any,
        *,
        query_param: str = "locale",
        cookie_name: str = "langsys_locale",
        supported: Optional[Sequence[str]] = None,
    ) -> None:
        self.app = app
        self.query_param = query_param
        self.cookie_name = cookie_name
        self.supported = list(supported) if supported else []

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = get_client()
        locale = self._resolve(scope, client)
        token = set_current_locale(locale) if locale else None
        # SRV-3 — the core holds whatever this request queues until the scope ends, whoever
        # flushes in the meantime: its debounce timer or another request's flush.
        held = client.begin_request_scope()

        async def send_then_release(message: dict[str, Any]) -> None:
            await send(message)
            if message["type"] == "http.response.body" and not message.get("more_body"):
                client.end_request_scope(held)

        completed = False
        try:
            await self.app(scope, receive, send_then_release)
            completed = True
        finally:
            if token is not None:
                reset_current_locale(token)
            # Idempotent; covers a request that raised or sent no body. A raised request's
            # misses are released here and the core's debounce sends them: a flush now would
            # run before the error response an outer middleware has yet to send.
            client.end_request_scope(held)
            try:
                if completed:
                    await self._flush(client)
            finally:
                # GATE-3 — the request is the boundary, and only this layer can see it.
                client.reset_write_decision()

    async def _flush(self, client: LangsysClient) -> None:
        # REG-3 / SRV-3 — the end of this request's context, after its response was sent.
        # Most requests queue nothing, so skip the threadpool hop for those.
        if not client.has_pending:
            return
        try:
            await run_in_threadpool(client.flush_pending)
        except Exception as exc:  # the response is already out; never raise past it
            logger.warning("langsys: flushing at the end of the request failed: %s", exc)

    def _resolve(self, scope: dict[str, Any], client: LangsysClient) -> str:
        # Header bytes are latin-1 on the wire: decoding them as UTF-8 raised on any
        # non-UTF-8 byte and turned the whole request into a 500.
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers") or []
        }
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))

        cookie: Optional[str] = None
        if headers.get("cookie"):
            jar: SimpleCookie = SimpleCookie()
            with contextlib.suppress(CookieError):
                jar.load(headers["cookie"])
            morsel = jar.get(self.cookie_name)
            cookie = morsel.value if morsel else None

        # Every candidate goes through the same core matcher, so `supported` constrains
        # an explicit choice exactly as it constrains Accept-Language — an unsupported
        # value falls through rather than reaching the API as a locale.
        candidates = (
            query.get(self.query_param, [None])[0],
            cookie,
            headers.get("accept-language"),
        )
        for candidate in candidates:
            if candidate:
                match = client.detect_preferred_locale(candidate, self.supported or None)
                if match:
                    return match
        return ""
