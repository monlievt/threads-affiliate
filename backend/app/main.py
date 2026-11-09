"""app/main.py — FastAPI application entry point.

Responsibilities:
- Create and configure the FastAPI app
- Configure structured logging
- Attach SlowAPI rate limiter (global; per-route limits added in later tickets)
- Include API routers
- Log kill switch state at startup
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api.analytics import router as analytics_router
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
from app.config import settings
from app.core.logging import configure_logging, get_logger
from app.db.session import AsyncSessionLocal
from app.safety.killswitch import ensure_kill_switch_initialized
from app.scheduler.reconciliation import run_startup_reconciliation

# ---------------------------------------------------------------------------
# Logging — configure before any logger usage
# ---------------------------------------------------------------------------
configure_logging(app_env=settings.APP_ENV)
log = get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate limiter (global; per-route decorators added in later tickets)
# ---------------------------------------------------------------------------
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan: startup → yield → shutdown."""
    # Ensure kill switch is initialized in database and run startup reconciliation
    try:
        async with AsyncSessionLocal() as session:
            await ensure_kill_switch_initialized(session)
            await run_startup_reconciliation(session)
    except Exception as exc:
        log.warning("Could not initialize kill switch or run startup reconciliation in DB", error=str(exc))

    # Startup logging
    if settings.KILL_SWITCH_ON_START:
        log.warning(
            "Kill switch ON — system will not publish until manually enabled",
            kill_switch="on",
            env=settings.APP_ENV,
        )
    else:
        log.info("Kill switch OFF — system is armed for publishing", kill_switch="off")

    log.info(
        "Application started",
        env=settings.APP_ENV,
        database_url=settings.DATABASE_URL,
    )

    yield

    # Shutdown
    log.info("Application shutting down")


# ---------------------------------------------------------------------------
# App instance
# ---------------------------------------------------------------------------
app = FastAPI(
    title="Threads Affiliate Automation API",
    description="Backend API for Threads affiliate content automation.",
    version="0.1.0",
    lifespan=lifespan,
    # Disable docs in production for security
    docs_url=None if settings.is_production else "/docs",
    redoc_url=None if settings.is_production else "/redoc",
)

# Attach rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------
app.include_router(system_router)
app.include_router(auth_router)
app.include_router(oauth_router)
app.include_router(niches_router)
app.include_router(products_router)
app.include_router(styles_router)
app.include_router(personas_router)
app.include_router(drafts_router)
app.include_router(schedule_router)
app.include_router(comments_router)
app.include_router(analytics_router)
