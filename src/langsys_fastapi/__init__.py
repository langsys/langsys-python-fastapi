"""FastAPI integration for Langsys — a thin wrapper over the ``langsys`` Python SDK.

Setup::

    from fastapi import FastAPI
    from langsys_fastapi import LangsysMiddleware, configure, at

    configure(api_key="…", project_id="…", base_locale="en-US")  # or LANGSYS_* env vars
    app = FastAPI()
    app.add_middleware(LangsysMiddleware, supported=["en-US", "es-ES"])

    @app.get("/save")
    async def save():
        return {"label": await at("Save", "UI")}

The base SDK is synchronous; ``at()`` runs it in a threadpool so it never blocks the
event loop. In synchronous ``def`` endpoints you can call ``t()`` directly.
"""

from __future__ import annotations

from .client import at, configure, get_client, reset_client, set_client, t
from .deps import current_locale, get_langsys
from .locale import get_current_locale, set_current_locale
from .middleware import LangsysMiddleware

__all__ = [
    "LangsysMiddleware",
    "configure",
    "t",
    "at",
    "get_client",
    "set_client",
    "reset_client",
    "get_langsys",
    "current_locale",
    "get_current_locale",
    "set_current_locale",
]
