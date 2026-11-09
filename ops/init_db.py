"""ops/init_db.py — Initialize local database and seed default data."""

import asyncio
from pathlib import Path
import sys

# Ensure backend root is in sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.db.models import Account, Base
from app.db.seed import seed_initial_styles
from app.db.session import engine, AsyncSessionLocal
from app.core.clock import utc_now_iso
from app.core.crypto import encrypt_token
from sqlalchemy import select


async def main():
    print("=== Initializing SQLite Database ===")
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Create tables
    async with engine.begin() as conn:
        print("Creating all tables in data/app.db...")
        await conn.run_sync(Base.metadata.create_all)

    # 2. Seed styles & kill switch
    async with AsyncSessionLocal() as session:
        print("Seeding initial styles and system state...")
        inserted_styles = await seed_initial_styles(session)
        print(f"Seeded {inserted_styles} styles.")

        # 3. Seed primary operator account if none exists
        existing_acc = await session.scalar(select(Account).limit(1))
        if not existing_acc:
            print("Creating initial primary operator account (@threads_curator)...")
            account = Account(
                id="acc_primary_001",
                username="threads_curator",
                display_name="Threads Curator (US Audience)",
                country_code="US",
                timezone="America/New_York",
                active_hours_start=9,
                active_hours_end=21,
                token_encrypted=encrypt_token("initial_mock_threads_token"),
                token_expires_at="2099-01-01T00:00:00Z",
                connected_at=utc_now_iso(),
                warmup_started_at=utc_now_iso(),
                automation_mode="manual_approve",
                sample_review_pct=30,
                status="active",
            )
            session.add(account)
            await session.commit()
            print("Primary operator account created.")

    print("✅ Database initialization complete: data/app.db ready.")


if __name__ == "__main__":
    asyncio.run(main())
