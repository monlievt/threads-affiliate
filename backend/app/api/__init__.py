"""app/api/__init__.py — API routers package."""

from app.api.auth import router as auth_router
from app.api.oauth import router as oauth_router
from app.api.system import router as system_router

__all__ = ["auth_router", "oauth_router", "system_router"]
