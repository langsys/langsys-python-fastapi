"""FastAPI dependency helpers.

Usage::

    from fastapi import Depends
    from langsys import LangsysClient
    from langsys_fastapi import get_langsys, get_current_locale

    @app.get("/greeting")
    def greeting(langsys: LangsysClient = Depends(get_langsys)):
        return {"text": langsys.translate("Save", category="UI")}
"""

from __future__ import annotations

from langsys import LangsysClient

from .client import get_client
from .locale import get_current_locale


def get_langsys() -> LangsysClient:
    """Dependency returning the shared client (locale already resolved by the middleware)."""
    return get_client()


def current_locale() -> str:
    """Dependency returning the resolved locale for the current request."""
    return get_current_locale()
