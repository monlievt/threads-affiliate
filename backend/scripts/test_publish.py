"""scripts/test_publish.py — Manual test publish script through minimal guard.

Usage:
  # Using FakeThreadsClient for safe local dry-run
  python -m scripts.test_publish --fake --text "Testing safe publishing pipeline via Fake client"

  # Real Threads publication (requires connected account & disarmed kill switch)
  python -m scripts.test_publish --account-id <id> --text "Hello Threads!"
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.clock import utc_now_iso
from app.core.crypto import encrypt_token
from app.core.logging import configure_logging, get_logger
from app.db.models import Account, AuditLog
from app.db.session import AsyncSessionLocal
from app.safety.killswitch import get_kill_switch_status, is_kill_switch_active, set_kill_switch
from app.threads.fake import FakeThreadsClient
from app.threads.publisher import publish_single_post

configure_logging()
logger = get_logger("test_publish_script")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Manual test publish script through minimal guard.")
    parser.add_argument("--account-id", type=str, default=None, help="Target account ID in DB.")
    parser.add_argument(
        "--text",
        type=str,
        default="Threads Affiliate test post: testing safe publishing pipeline.",
        help="Post text content (max 500 characters).",
    )
    parser.add_argument(
        "--fake",
        action="store_true",
        help="Use FakeThreadsClient instead of calling Meta API (safe for local verification).",
    )
    parser.add_argument(
        "--disarm-kill-switch",
        action="store_true",
        help="Explicitly disarm the global kill switch before publishing.",
    )

    args = parser.parse_args()

    async with AsyncSessionLocal() as session:
        # 1. Check or handle kill switch
        ks_status = await get_kill_switch_status(session)
        print(f"[*] Current Kill Switch Status: {ks_status['status'].upper()} (Reason: {ks_status['reason']})")

        if ks_status["active"]:
            if args.disarm_kill_switch:
                print("[*] Disarming kill switch as requested (--disarm-kill-switch)...")
                await set_kill_switch(
                    session,
                    active=False,
                    reason="Operator manual test publish script",
                    actor="operator_cli",
                )
                print("[+] Kill switch successfully disarmed.")
            else:
                print(
                    "\n[BLOCKED] Kill switch is ON. The system will NOT publish while kill switch is engaged.\n"
                    "To disarm, pass `--disarm-kill-switch` or toggle via dashboard/API.\n",
                    file=sys.stderr,
                )
                return 1

        # 2. Resolve account
        account: Account | None = None
        if args.account_id:
            account = await session.scalar(select(Account).where(Account.id == args.account_id))
            if not account:
                print(f"[!] Account ID {args.account_id!r} not found in database.", file=sys.stderr)
                return 1
        else:
            # Pick first available account or create a mock account if running --fake
            account = await session.scalar(select(Account).limit(1))
            if not account:
                if args.fake:
                    print("[*] No existing account found. Creating temporary test account for --fake mode...")
                    account = Account(
                        threads_user_id="fake_user_001",
                        username="test_affiliate_operator",
                        token_encrypted=encrypt_token("mock_token_for_fake_test"),
                        country_code="US",
                        timezone="America/New_York",
                        connected_at=utc_now_iso(),
                    )
                    session.add(account)
                    await session.commit()
                    await session.refresh(account)
                    print(f"[+] Created test account ID: {account.id}")
                else:
                    print(
                        "[!] No connected account found in DB. Complete OAuth flow or run with `--fake`.",
                        file=sys.stderr,
                    )
                    return 1

        print(f"[*] Publishing post as account: {account.username or account.threads_user_id} (ID: {account.id})")
        print(f"[*] Content ({len(args.text)} chars): {args.text!r}")

        # 3. Resolve client
        client = None
        if args.fake:
            print("[*] Using FakeThreadsClient (simulated network)")
            client = FakeThreadsClient(
                user_id=account.threads_user_id or "fake_user",
                username=account.username or "fake_curator",
            )

        # 4. Execute safe publish
        try:
            post = await publish_single_post(
                session,
                account_id=account.id,
                text=args.text,
                client=client,
                actor="operator_cli",
            )
        except Exception as exc:
            print(f"\n[ERROR] Publish failed: {exc}", file=sys.stderr)
            return 1

        print("\n" + "=" * 60)
        print("[SUCCESS] Post published through minimal guard!")
        print(f"  Post ID:          {post.id}")
        print(f"  Threads Media ID: {post.threads_media_id}")
        print(f"  Creation ID:      {post.creation_id}")
        print(f"  Permalink:        {post.permalink}")
        print(f"  Published At:     {post.published_at}")
        print("=" * 60)

        # Verify audit log
        latest_audit = await session.scalar(
            select(AuditLog).where(AuditLog.entity_id == post.id).order_by(AuditLog.at.desc())
        )
        if latest_audit:
            print(f"[+] Audit log verified: action={latest_audit.action} actor={latest_audit.actor} at={latest_audit.at}\n")

    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))

