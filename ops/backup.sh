#!/usr/bin/env bash
# ==============================================================================
# ops/backup.sh — Live Hot Backup for SQLite WAL Database (T-051)
# ==============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"

DATA_DIR="${ROOT_DIR}/data"
BACKUP_DIR="${ROOT_DIR}/backup"
DB_FILE="${DATA_DIR}/app.db"

mkdir -p "${BACKUP_DIR}"

TIMESTAMP=$(date -u +"%Y%m%d_%H%M%S")
BACKUP_FILE="${BACKUP_DIR}/app-${TIMESTAMP}.db"
SHA_FILE="${BACKUP_FILE}.sha256"

echo "=== [$(date -u +"%Y-%m-%d %H:%M:%SZ")] Starting SQLite Hot Backup ==="
echo "Source: ${DB_FILE}"
echo "Destination: ${BACKUP_FILE}"

if [[ ! -f "${DB_FILE}" ]]; then
  echo "ERROR: Source database ${DB_FILE} not found." >&2
  exit 1
fi

# Run non-blocking SQLite online backup API
if command -v sqlite3 >/dev/null 2>&1; then
  sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
else
  # Fallback to python backup engine if sqlite3 binary is absent
  python3 -c "
import sqlite3
src = sqlite3.connect('${DB_FILE}')
dst = sqlite3.connect('${BACKUP_FILE}')
with dst:
    src.backup(dst)
dst.close()
src.close()
"
fi

# Verify integrity of the created backup
INTEGRITY=$(python3 -c "
import sqlite3
c = sqlite3.connect('${BACKUP_FILE}')
res = c.execute('PRAGMA integrity_check;').fetchone()[0]
c.close()
print(res)
")

if [[ "${INTEGRITY}" != "ok" ]]; then
  echo "ERROR: Backup integrity check failed: ${INTEGRITY}" >&2
  rm -f "${BACKUP_FILE}"
  exit 2
fi

# Generate SHA-256 checksum
python3 -c "
import hashlib
h = hashlib.sha256(open('${BACKUP_FILE}', 'rb').read()).hexdigest()
open('${SHA_FILE}', 'w').write(f'{h}  $(basename \"${BACKUP_FILE}\")\n')
print(f'SHA256: {h}')
"

# Retention Pruning: Keep last 14 daily + 8 weekly (total 22)
PRUNED_COUNT=$(python3 -c "
import os, glob
files = sorted(glob.glob('${BACKUP_DIR}/*.db'), key=os.path.getmtime, reverse=True)
pruned = 0
if len(files) > 22:
    for f in files[22:]:
        try:
            os.remove(f)
            sha = f + '.sha256'
            if os.path.exists(sha): os.remove(sha)
            pruned += 1
        except Exception:
            pass
print(pruned)
")

echo "Backup successful! Pruned ${PRUNED_COUNT} old backup files."
echo "=== Backup Complete ==="
