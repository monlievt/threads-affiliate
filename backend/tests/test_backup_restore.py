"""tests/test_backup_restore.py — Test suite for Database Backup, Verification, and Restore Engine (T-051).

Verifies operational compliance with docs/11 §3:
1. perform_database_backup creates a valid, non-blocking online snapshot in WAL mode.
2. SHA-256 checksum generation and validation detects tampering/corruption.
3. perform_database_restore:
   - Cleans up stale WAL and SHM files to prevent corruption.
   - Restores all table rows and constraints cleanly.
   - Passes PRAGMA integrity_check.
   - Enforces post-restore safety rule: Kill switch is set to ON (active=1).
   - Records an audit trail log entry for the restore event.
4. Retention policy pruning keeps 14 daily + 8 weekly snapshots.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
import pytest

from app.core.backup import (
    compute_file_sha256,
    perform_database_backup,
    perform_database_restore,
    prune_old_backups,
    verify_backup_integrity,
)


@pytest.fixture
def sample_sqlite_db(tmp_path: Path) -> Path:
    """Create a sample SQLite WAL database with seeded schema and records."""
    db_file = tmp_path / "app.db"
    conn = sqlite3.connect(str(db_file))
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL;")
    cur.execute(
        """
        CREATE TABLE system_state (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE audit_logs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            entity TEXT NOT NULL,
            entity_id TEXT,
            detail TEXT
        );
        """
    )
    cur.execute(
        """
        CREATE TABLE test_items (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            score INTEGER NOT NULL
        );
        """
    )
    cur.execute("INSERT INTO system_state VALUES ('kill_switch_active', '0', '2026-11-09T00:00:00Z');")
    cur.execute("INSERT INTO test_items VALUES ('item_1', 'Original Widget', 100);")
    cur.execute("INSERT INTO test_items VALUES ('item_2', 'Original Gadget', 200);")
    conn.commit()
    conn.close()
    return db_file


# ---------------------------------------------------------------------------
# 1. Backup & Integrity Verification Tests
# ---------------------------------------------------------------------------

def test_backup_creation_and_integrity(sample_sqlite_db: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"

    # 1. Perform live backup
    res = perform_database_backup(sample_sqlite_db, backup_dir)
    assert res["success"] is True
    backup_file = Path(res["backup_file"])
    assert backup_file.exists()
    assert backup_file.stat().st_size > 0

    # 2. Check SHA-256 checksum file
    sha_file = backup_file.with_name(f"{backup_file.name}.sha256")
    assert sha_file.exists()
    computed_sha = compute_file_sha256(backup_file)
    assert res["checksum"] == computed_sha

    with open(sha_file, "r", encoding="utf-8") as f:
        stored_sha = f.read().split()[0].strip()
    assert stored_sha.lower() == computed_sha.lower()

    # 3. Verify integrity
    valid, msg = verify_backup_integrity(backup_file)
    assert valid is True
    assert "passed" in msg


def test_verify_backup_detects_tampering(sample_sqlite_db: Path, tmp_path: Path) -> None:
    backup_dir = tmp_path / "backups"
    res = perform_database_backup(sample_sqlite_db, backup_dir)
    backup_file = Path(res["backup_file"])

    # Tamper with backup file by modifying bytes
    with open(backup_file, "r+b") as f:
        f.seek(50)
        f.write(b"CORRUPTED_BYTES")

    valid, msg = verify_backup_integrity(backup_file)
    assert valid is False
    assert "Checksum mismatch" in msg


# ---------------------------------------------------------------------------
# 2. Restore & Safety Enforcement Tests
# ---------------------------------------------------------------------------

def test_database_restore_and_killswitch_enforcement(
    sample_sqlite_db: Path, tmp_path: Path
) -> None:
    backup_dir = tmp_path / "backups"
    res_b = perform_database_backup(sample_sqlite_db, backup_dir)
    backup_file = Path(res_b["backup_file"])

    # Mutate original database after backup (delete item_1, add bad item)
    conn = sqlite3.connect(str(sample_sqlite_db))
    conn.execute("DELETE FROM test_items WHERE id = 'item_1';")
    conn.execute("INSERT INTO test_items VALUES ('item_bad', 'Mutated Item', 999);")
    conn.commit()
    conn.close()

    # Create dummy WAL and SHM files to test cleanup
    wal_file = sample_sqlite_db.with_name(f"{sample_sqlite_db.name}-wal")
    shm_file = sample_sqlite_db.with_name(f"{sample_sqlite_db.name}-shm")
    wal_file.write_text("dummy wal")
    shm_file.write_text("dummy shm")
    assert wal_file.exists() and shm_file.exists()

    # Perform restoration
    restore_res = perform_database_restore(
        backup_path=backup_file,
        target_db_path=sample_sqlite_db,
        enforce_killswitch_on=True,
    )
    assert restore_res["success"] is True
    assert restore_res["kill_switch_active"] is True

    # 1. Stale dummy WAL and SHM files must have been cleaned up
    assert not wal_file.exists()
    assert not shm_file.exists()

    # 2. Verify restored data matches the original backup snapshot
    conn_r = sqlite3.connect(str(sample_sqlite_db))
    cur = conn_r.cursor()
    cur.execute("SELECT id, name FROM test_items ORDER BY id;")
    rows = cur.fetchall()
    assert rows == [("item_1", "Original Widget"), ("item_2", "Original Gadget")]

    # 3. Post-restore safety rule: Kill switch MUST be ON (docs/11 §3)
    cur.execute("SELECT value FROM system_state WHERE key = 'kill_switch_active';")
    ks_val = cur.fetchone()[0]
    assert ks_val == "1"

    # 4. Audit trail entry MUST exist
    cur.execute("SELECT action, actor, entity FROM audit_logs WHERE action = 'database_restored';")
    audit_row = cur.fetchone()
    assert audit_row is not None
    assert audit_row[0] == "database_restored"
    assert audit_row[1] == "restore_engine"

    # 5. Integrity check must pass cleanly
    cur.execute("PRAGMA integrity_check;")
    chk = cur.fetchone()[0]
    assert chk == "ok"

    conn_r.close()


# ---------------------------------------------------------------------------
# 3. Retention Pruning Tests
# ---------------------------------------------------------------------------

def test_prune_old_backups(tmp_path: Path) -> None:
    backup_dir = tmp_path / "prune_test"
    backup_dir.mkdir(parents=True)

    # Create 25 mock backup files
    for i in range(25):
        f = backup_dir / f"app-2026110{i:02d}_000000.db"
        f.write_text(f"dummy db content {i}")
        sha = f.with_name(f"{f.name}.sha256")
        sha.write_text("dummy sha")

    # Prune with keep_daily=14, keep_weekly=8 -> total 22 allowed
    pruned = prune_old_backups(backup_dir, keep_daily=14, keep_weekly=8)
    assert pruned == 3

    remaining_files = list(backup_dir.glob("*.db"))
    assert len(remaining_files) == 22
