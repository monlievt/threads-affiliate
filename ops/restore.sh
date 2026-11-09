#!/usr/bin/env bash
# ==============================================================================
# ops/restore.sh — Safe Database Restore & Disaster Recovery (T-051)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DATA_DIR="${ROOT_DIR}/data"
BACKUP_DIR="${ROOT_DIR}/backup"
TARGET_DB="${DATA_DIR}/app.db"

# Backup file selection: from argument, or latest available
BACKUP_FILE="${1:-}"
if [[ -z "${BACKUP_FILE}" ]]; then
  LATEST_BACKUP=$(ls -t "${BACKUP_DIR}"/app-*.db 2>/dev/null | head -n 1 || true)
  if [[ -z "${LATEST_BACKUP}" ]]; then
    echo "ERROR: No backup files found in ${BACKUP_DIR}." >&2
    echo "Usage: $0 [path/to/backup.db]" >&2
    exit 1
  fi
  BACKUP_FILE="${LATEST_BACKUP}"
fi

echo "=== [$(date -u +"%Y-%m-%d %H:%M:%SZ")] Starting Database Restore ==="
echo "Selected Backup: ${BACKUP_FILE}"
echo "Target: ${TARGET_DB}"

if [[ ! -f "${BACKUP_FILE}" ]]; then
  echo "ERROR: Backup file ${BACKUP_FILE} does not exist." >&2
  exit 1
fi

# 1. Verify Checksum
SHA_FILE="${BACKUP_FILE}.sha256"
if [[ -f "${SHA_FILE}" ]]; then
  echo "Verifying SHA-256 checksum..."
  python3 -c "
import hashlib
expected = open('${SHA_FILE}').read().split()[0].strip()
actual = hashlib.sha256(open('${BACKUP_FILE}', 'rb').read()).hexdigest()
if expected.lower() != actual.lower():
    raise SystemExit(f'CHECKSUM MISMATCH! Expected: {expected}, Got: {actual}')
print('Checksum verified: OK')
"
fi

# 2. Verify Backup SQLite Integrity
echo "Verifying backup database integrity..."
python3 -c "
import sqlite3
c = sqlite3.connect('${BACKUP_FILE}')
res = c.execute('PRAGMA integrity_check;').fetchone()[0]
c.close()
if res != 'ok':
    raise SystemExit(f'INTEGRITY CHECK FAILED: {res}')
print('Database structure: OK')
"

# 3. Create pre-restore safety copy of current target DB if it exists
if [[ -f "${TARGET_DB}" ]]; then
  TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
  SAFETY_COPY="${TARGET_DB}.pre_restore_${TIMESTAMP}"
  echo "Creating safety snapshot of current DB: ${SAFETY_COPY}"
  cp "${TARGET_DB}" "${SAFETY_COPY}"
fi

# 4. Remove stale WAL & SHM files to prevent WAL corruption
echo "Cleaning up stale WAL and shared-memory files..."
rm -f "${TARGET_DB}-wal" "${TARGET_DB}-shm"

# 5. Restore Database
echo "Copying backup to target..."
cp "${BACKUP_FILE}" "${TARGET_DB}"

# 6. Post-restore safety enforcement (docs/11 §3)
# ENFORCE KILL SWITCH ON & LOG AUDIT TRAIL
echo "Enforcing Kill Switch ON and logging audit event..."
python3 -c "
import sqlite3, datetime
c = sqlite3.connect('${TARGET_DB}')
now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
c.execute('PRAGMA journal_mode=WAL;')
c.execute('PRAGMA wal_autocheckpoint=100;')
c.execute(\"UPDATE system_state SET value = '1', updated_at = ? WHERE key = 'kill_switch_active';\", (now_iso,))
c.execute('''
INSERT INTO audit_logs (id, created_at, actor, action, entity, entity_id, detail)
VALUES (?, ?, 'restore_script', 'database_restored', 'database', 'app.db', ?);
''', (f'restore_{now_iso}', now_iso, '{\"restored_from\": \"$(basename \"${BACKUP_FILE}\")\", \"kill_switch\": \"ON\"}'))
c.commit()
c.close()
"

# 7. Final Verification
FINAL_CHECK=$(python3 -c "
import sqlite3
c = sqlite3.connect('${TARGET_DB}')
res = c.execute('PRAGMA integrity_check;').fetchone()[0]
c.close()
print(res)
")

if [[ "${FINAL_CHECK}" != "ok" ]]; then
  echo "ERROR: Restored database failed integrity check: ${FINAL_CHECK}" >&2
  exit 3
fi

echo "=== Restore Complete Successfully! ==="
echo "SAFETY REMINDER: Kill Switch is set to ON (active=1)."
echo "Verify system health at /health and review publishing drafts before disarming."
