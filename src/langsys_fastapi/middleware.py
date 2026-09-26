"""Request-locale ASGI middleware — and the request boundary the core cannot see.

For each HTTP request it:

1. resolves the locale through the core's ``resolve_request_locale`` (SRV-6): the URL — a
   path segment, the subdomain or ``?locale=``, wherever the app routes by it — then the
   ``langsys_locale`` cookie, then ``Accept-Language``, then the project's
   base locale, each candidate validated against the locales the project serves. The response
   carries the ``Vary`` headers that choice depended on, and the middleware never writes the
   cookie. The locale is exposed to translations through the request-scoped context variable;
2. opens the core's request scope, so nothing the request queues can be sent — by the core's
   debounce timer or by another request's flush — before its response is out. The scope ends
   once the final response body has been sent, and the middleware then hands the queue to the
   core's public ``flush_pending()``. Whether that registers, holds (the capability could not be
   determined) or discards (the server said no) is the core's decision, taken at its send
   site: this middleware never reads or branches on capability;
3. forgets the observed write decision with ``reset_write_decision()``, so it cannot outlive
   the request.

Raw ASGI rather than ``BaseHTTPMiddleware``, so the context variable set here reliably
propagates into the endpoint, and so "the app has returned" means the final response message
has been sent.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Mapping
from http.cookies import CookieError, SimpleCookie
from typing import Any, Optional
from urllib.parse import parse_qs

from langsys import LangsysClient
from langsys.request_locale import LocaleChoice
from starlette.concurrency import run_in_threadpool

from .client import get_client
from .locale import reset_current_locale, set_current_locale

logger = logging.getLogger("langsys")


class LangsysMiddleware:
    """Where the app keeps the locale in a request — wiring, not configuration (SRV-6):

    * ``path_segment`` — the index of the path segment the app routes the locale by
      (``0`` for ``/es/pricing``);
    * ``subdomain`` — the first label of the host carries it (``es.example.com``);
    * ``query_param`` — the query parameter that carries it;
    * ``cookie_name`` — the cookie the app keeps it in; ``None`` when there is none, so no
      response varies on one;
    * ``state_key`` — the ``request.state`` attribute an app's own middleware, running before
      this one, sets once it has resolved the locale itself. That locale is served as the app
      resolved it (the core validates and maps it) and nothing else is consulted.

    The URL's value is the first of the URL knobs present, in that order; the core validates it."""

    def __init__(
        self,
        app: Any,
        *,
        query_param: str = "locale",
        cookie_name: Optional[str] = "langsys_locale",
        path_segment: Optional[int] = None,
        subdomain: bool = False,
        state_key: Optional[str] = "locale",
    ) -> None:
        self.app = app
        self.query_param = query_param
        self.cookie_name = cookie_name
        self.path_segment = path_segment
        self.subdomain = subdomain
        self.state_key = state_key

    async def __call__(self, scope: dict[str, Any], receive: Any, send: Any) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        client = get_client()
        choice = await run_in_threadpool(self._resolve, scope, client)
        token = set_current_locale(choice.locale) if choice.locale else None
        # SRV-3 — the core holds whatever this request queues until the scope ends, whoever
        # flushes in the meantime: its debounce timer or another request's flush.
        held = client.begin_request_scope()

        async def send_then_release(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.start" and choice.vary:
                message = {**message, "headers": _with_vary(message.get("headers"), choice.vary)}
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

    def _resolve(self, scope: dict[str, Any], client: LangsysClient) -> LocaleChoice:
        # Header bytes are latin-1 on the wire; a non-UTF-8 byte must not fail the request.
        headers = {
            name.decode("latin-1").lower(): value.decode("latin-1")
            for name, value in scope.get("headers") or []
        }
        query = parse_qs(scope.get("query_string", b"").decode("latin-1"))

        cookie: Optional[str] = None
        if self.cookie_name and headers.get("cookie"):
            jar: SimpleCookie = SimpleCookie()
            with contextlib.suppress(CookieError):
                jar.load(headers["cookie"])
            morsel = jar.get(self.cookie_name)
            cookie = morsel.value if morsel else None

        state = scope.get("state")
        app_locale = (
            state.get(self.state_key) if self.state_key and isinstance(state, Mapping) else None
        )
        return client.resolve_request_locale(
            framework=app_locale if isinstance(app_locale, str) and app_locale else None,
            url=self._url_locale(scope, headers, query),
            cookie=cookie,
            accept_language=headers.get("accept-language"),
            uses_cookie=self.cookie_name is not None,
        )

    def _url_locale(
        self, scope: dict[str, Any], headers: dict[str, str], query: dict[str, list[str]]
    ) -> Optional[str]:
        """The locale the app routes by in the URL, or None: a path segment, then the subdomain,
        then the query parameter — the first present. Validating it is the core's."""
        if self.path_segment is not None:
            segments = [part for part in str(scope.get("path") or "").split("/") if part]
            if len(segments) > self.path_segment:
                return segments[self.path_segment]
        if self.subdomain:
            label = _first_label(headers.get("host", ""))
            if label:
                return label
        return query.get(self.query_param, [None])[0]


def _first_label(host: str) -> Optional[str]:
    labels = host.split(":")[0].split(".")
    return labels[0] if len(labels) > 2 and labels[0] else None


def _with_vary(headers: Any, vary: tuple[str, ...]) -> list[tuple[bytes, bytes]]:
    """``headers`` with ``vary`` merged into its ``Vary``, keeping what the app already named."""
    kept: list[tuple[bytes, bytes]] = []
    named: list[str] = []
    for name, value in headers or []:
        if name.lower() == b"vary":
            named.extend(v.strip() for v in value.decode("latin-1").split(",") if v.strip())
        else:
            kept.append((name, value))
    lowered = {v.lower() for v in named}
    named.extend(v for v in vary if v.lower() not in lowered)
    return [*kept, (b"vary", ", ".join(named).encode("latin-1"))]
