"""The shared :class:`~langsys.LangsysClient`, configuration, and the ``t`` helpers."""

from __future__ import annotations

import threading
from typing import Any, Optional

from langsys import LangsysClient
from starlette.concurrency import run_in_threadpool

from .locale import ContextVarLocaleSource

_config: dict[str, Any] = {}
_client: Optional[LangsysClient] = None
_lock = threading.Lock()


def configure(
    *,
    api_key: Optional[str] = None,
    project_id: Optional[str] = None,
    api_url: Optional[str] = None,
    base_locale: Optional[str] = None,
    cache: Optional[Any] = None,
    cache_ttl: Optional[int] = None,
    timeout: Optional[float] = None,
    message_category: Optional[str] = None,
) -> None:
    """Configure Langsys (typically in a FastAPI startup handler).

    Any value left as ``None`` falls back to the ``LANGSYS_*`` environment variable, so
    calling this is optional if you configure entirely through the environment. Every
    option is the core client's own, passed through unchanged; ``api_url`` (or
    ``LANGSYS_API_URL``) points the client at a test double. Calling this again rebuilds
    the client, so a later call takes effect even after the first translation.
    """
    global _config
    _config = {
        key: value
        for key, value in {
            "api_key": api_key,
            "project_id": project_id,
            "api_url": api_url,
            "base_locale": base_locale,
            "cache": cache,
            "cache_ttl": cache_ttl,
            "timeout": timeout,
            "message_category": message_category,
        }.items()
        if value is not None
    }
    reset_client()


def get_client() -> LangsysClient:
    """Return the process-wide client (built once). Locale comes from the request-scoped
    context variable, so the shared instance is safe across concurrent requests. Every
    other option is the core's default — this binding does not schedule sends."""
    global _client
    if _client is None:
        with _lock:
            if _client is None:
                _client = LangsysClient(locale_source=ContextVarLocaleSource(), **_config)
    return _client


def set_client(client: LangsysClient) -> None:
    """Use a caller-built client (advanced setups / tests). It should read its locale
    from :class:`ContextVarLocaleSource`."""
    global _client
    _client = client


def reset_client() -> None:
    """Retire the shared client, handing its queue to the core first.

    The client's execution context ends here, so whatever it still holds goes to the
    core's ``flush_pending()`` — registered, held or discarded as the server decides —
    rather than being closed away unsent (REG-3).
    """
    global _client
    with _lock:
        client, _client = _client, None
    if client is None:
        return
    try:
        client.flush_pending()
    finally:
        client.close()


def t(phrase: str, category: Optional[str] = None, **params: Any) -> str:
    """Translate ``phrase`` for the current request locale (synchronous).

    Safe to call directly from a synchronous ``def`` endpoint/dependency — FastAPI runs
    those in a threadpool. From an ``async def`` endpoint, prefer :func:`at`.

    ``phrase`` and ``category`` are this function's own arguments, so a placeholder with
    either name cannot be passed as a keyword here — ``category=`` is taken as the
    category. For those, call the core directly:
    ``get_langsys().translate(phrase, category=..., params={"category": ...})``.
    """
    return get_client().translate(phrase, category=category, params=params or None)


async def at(phrase: str, category: Optional[str] = None, **params: Any) -> str:
    """Async translate — runs the (blocking) SDK call in a threadpool so it never blocks
    the event loop. Use from ``async def`` endpoints."""
    return await run_in_threadpool(t, phrase, category, **params)
