"""app/api/__init__.py — API routers package."""

from app.api.auth import router as auth_router
from app.api.system import router as system_router

__all__ = ["auth_router", "system_router"]
