"""Per-request locale, held in a ``ContextVar`` (async- and thread-safe).

The integration shares a single :class:`~langsys.LangsysClient`; the client reads its
locale from this context variable through :class:`ContextVarLocaleSource` (the SDK's
``LocaleSource`` binding point), so one shared instance is safe under FastAPI's
concurrency. The middleware sets it per request.
"""

from __future__ import annotations

import contextvars
from typing import Callable

_current_locale: contextvars.ContextVar[str] = contextvars.ContextVar(
    "langsys_current_locale", default=""
)


def get_current_locale() -> str:
    return _current_locale.get()


def set_current_locale(locale: str) -> contextvars.Token[str]:
    return _current_locale.set(locale)


def reset_current_locale(token: contextvars.Token[str]) -> None:
    _current_locale.reset(token)


class ContextVarLocaleSource:
    """A ``LocaleSource`` backed by the request-scoped context variable. ``get()`` returns
    ``""`` when unset so the SDK falls back to the configured / project base locale."""

    def get(self) -> str:
        return _current_locale.get()

    def subscribe(self, callback: Callable[[str], None]) -> Callable[[], None]:
        callback(self.get())
        return lambda: None
