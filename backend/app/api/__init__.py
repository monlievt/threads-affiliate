"""app/api/__init__.py — API routers package."""

from app.api.auth import router as auth_router
from app.api.comments import router as comments_router
from app.api.drafts import router as drafts_router
from app.api.niches import router as niches_router
from app.api.oauth import router as oauth_router
from app.api.personas import router as personas_router
from app.api.products import router as products_router
from app.api.schedule import router as schedule_router
from app.api.styles import router as styles_router
from app.api.system import router as system_router

__all__ = [
    "auth_router",
    "comments_router",
    "drafts_router",
    "niches_router",
    "oauth_router",
    "personas_router",
    "products_router",
    "schedule_router",
    "styles_router",
    "system_router",
]
