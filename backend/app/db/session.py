"""app/db/session.py — Async SQLAlchemy engine and session factory.

SQLite WAL mode is configured at connection time:
  - PRAGMA journal_mode=WAL
  - PRAGMA foreign_keys=ON
  - PRAGMA wal_autocheckpoint=100
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncConnection,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from app.config import settings

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_engine_kwargs: dict = {
    "connect_args": {"check_same_thread": False},
    "echo": False,
}

# Use StaticPool for SQLite in-process (required for aiosqlite in tests)
if settings.DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["poolclass"] = StaticPool

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)


@event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_connection: object, connection_record: object) -> None:  # noqa: ARG001
    """Configure SQLite WAL mode and foreign keys on every new connection."""
    cursor = dbapi_connection.cursor()  # type: ignore[union-attr]
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA wal_autocheckpoint=100")
    cursor.close()


# ---------------------------------------------------------------------------
# Session factory
# ---------------------------------------------------------------------------

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
    autocommit=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async DB session, closes after request."""
    async with AsyncSessionLocal() as session:
        yield session


async def check_db_connection() -> bool:
    """Health check: returns True if DB is reachable, False otherwise."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
