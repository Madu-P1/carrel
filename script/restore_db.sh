#!/usr/bin/env bash
# restore_db.sh — point-in-time restore from a backup created by
# backup_db.sh.
#
# Usage:
#   script/restore_db.sh <backup-file.db.bz2>
#   script/restore_db.sh latest               # newest in daily/
#
# Always quits Carrel first (you don't want uvicorn writing while
# we swap files underneath it). Moves the current DB aside as
# einstein_tutor.db.pre-restore-<ts> rather than deleting, so a bad
# restore is reversible by hand.

set -euo pipefail

DEFAULT_BASE="${HOME}/Library/Application Support/Carrel"
CARREL_BASE="${CARREL_BASE_DIR:-$DEFAULT_BASE}"
DB_PATH="${CARREL_DB_PATH:-$CARREL_BASE/data/einstein_tutor.db}"
BACKUP_DIR="${CARREL_BACKUP_DIR:-$CARREL_BASE/backups}"

usage() {
  cat >&2 <<'EOF'
usage: restore_db.sh <backup-file.db.bz2 | latest>

  latest    Restore the most recent backup in $BACKUP_DIR/daily/

Environment:
  CARREL_BASE_DIR    Override the default ~/Library/Application Support/Carrel
  CARREL_DB_PATH     Override the DB path
  CARREL_BACKUP_DIR  Override the backup directory
EOF
}

if [[ $# -ne 1 ]]; then
  usage; exit 2
fi

target="$1"
if [[ "$target" == "latest" ]]; then
  target="$(ls -1t "$BACKUP_DIR"/daily/einstein_tutor-*.db.bz2 2>/dev/null | head -1)"
  if [[ -z "$target" ]]; then
    echo "restore_db: no backups in $BACKUP_DIR/daily" >&2
    exit 1
  fi
fi

if [[ ! -f "$target" ]]; then
  echo "restore_db: $target not found" >&2
  exit 1
fi

# Refuse to clobber a running uvicorn — the user would lose any
# uncommitted writes silently. Skipped during the CI drill which
# operates on a temp DB no production uvicorn touches.
if [[ "${CARREL_RESTORE_FORCE:-0}" != "1" ]] && pgrep -fl "uvicorn main:app" >/dev/null 2>&1; then
  echo "restore_db: uvicorn is running. Quit Carrel first." >&2
  echo "restore_db: (set CARREL_RESTORE_FORCE=1 to skip this check; only safe for tests)" >&2
  exit 1
fi

ts="$(date +%Y%m%d-%H%M%S)"
data_dir="$(dirname "$DB_PATH")"
mkdir -p "$data_dir"

if [[ -f "$DB_PATH" ]]; then
  mv "$DB_PATH" "$DB_PATH.pre-restore-$ts"
  echo "restore_db: existing DB moved to $DB_PATH.pre-restore-$ts"
fi
# Also move the WAL/SHM siblings — leaving them stale produces the
# infamous "database disk image is malformed" error on next open.
[[ -f "$DB_PATH-wal" ]] && mv "$DB_PATH-wal" "$DB_PATH-wal.pre-restore-$ts"
[[ -f "$DB_PATH-shm" ]] && mv "$DB_PATH-shm" "$DB_PATH-shm.pre-restore-$ts"

bunzip2 -kc "$target" > "$DB_PATH"

# Sanity check — fail loudly rather than handing back a corrupt DB.
result="$(sqlite3 "$DB_PATH" 'PRAGMA integrity_check;' | head -1)"
if [[ "$result" != "ok" ]]; then
  echo "restore_db: integrity check failed on restored DB: $result" >&2
  exit 1
fi

count="$(sqlite3 "$DB_PATH" 'SELECT COUNT(*) FROM documents;')"
echo "restore_db: restored from $target ($count documents)"
echo "restore_db: previous DB at $DB_PATH.pre-restore-$ts (delete after verifying)"
