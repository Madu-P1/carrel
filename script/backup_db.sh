#!/usr/bin/env bash
# backup_db.sh — point-in-time backup of the Carrel SQLite DB.
#
# Uses `sqlite3 .backup` (not `cp`) because the DB is hot — uvicorn
# may have a write transaction in flight. The backup API is the only
# safe way: it acquires a shared lock, copies pages atomically, and
# releases. Compatible with WAL mode.
#
# Defaults to ~/Library/Application Support/Carrel/backups/, retains
# 14 daily + 8 weekly snapshots. Override CARREL_BACKUP_DIR to relocate.
#
# Schedule (one of):
#   * launchd plist at ~/Library/LaunchAgents/com.madu.carrel.backup.plist
#   * cron: 0 3 * * * /path/to/Carrel/script/backup_db.sh
#   * GitHub Actions workflow_dispatch in CI for restore drills
#
# Restore: see script/restore_db.sh.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Default DB path matches services/runtime_paths defaults; override
# with CARREL_DB_PATH to back up a non-default location.
DEFAULT_BASE="${HOME}/Library/Application Support/Carrel"
CARREL_BASE="${CARREL_BASE_DIR:-$DEFAULT_BASE}"
DB_PATH="${CARREL_DB_PATH:-$CARREL_BASE/data/einstein_tutor.db}"
BACKUP_DIR="${CARREL_BACKUP_DIR:-$CARREL_BASE/backups}"

DAILY_RETENTION=14
WEEKLY_RETENTION=8

if [[ ! -f "$DB_PATH" ]]; then
  echo "backup_db: $DB_PATH not found; nothing to back up." >&2
  exit 0
fi

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/weekly"

ts="$(date +%Y%m%d-%H%M%S)"
weekday="$(date +%u)"  # 1=Mon..7=Sun
daily_path="$BACKUP_DIR/daily/einstein_tutor-$ts.db"
weekly_path="$BACKUP_DIR/weekly/einstein_tutor-$ts.db"

# `.backup` is the SQLite Online Backup API — atomic + lock-aware.
sqlite3 "$DB_PATH" ".backup '$daily_path'"

# Verify integrity before declaring success. A backup that opens but
# fails integrity-check is a silent disaster.
result="$(sqlite3 "$daily_path" 'PRAGMA integrity_check;' | head -1)"
if [[ "$result" != "ok" ]]; then
  echo "backup_db: integrity check failed for $daily_path: $result" >&2
  rm -f "$daily_path"
  exit 1
fi

# Compress with macOS-native bzip2 (smaller than gzip, available
# everywhere). Decompress with `bunzip2` or `tar xj`.
bzip2 -f "$daily_path"
daily_path="$daily_path.bz2"

# On Sundays, also keep a weekly copy that gets a longer retention.
# Hard-link instead of re-running .backup so we don't double-pay
# the I/O cost.
if [[ "$weekday" == "7" ]]; then
  ln -f "$daily_path" "$weekly_path.bz2"
fi

# Retention pruning — keep most-recent N, delete older.
prune() {
  local dir="$1" keep="$2"
  # ls -1t lists newest first; tail skips the first $keep.
  local victims
  victims=$(ls -1t "$dir"/einstein_tutor-*.db.bz2 2>/dev/null | tail -n +"$((keep + 1))" || true)
  if [[ -n "$victims" ]]; then
    echo "$victims" | xargs rm -f --
  fi
}

prune "$BACKUP_DIR/daily" "$DAILY_RETENTION"
prune "$BACKUP_DIR/weekly" "$WEEKLY_RETENTION"

size="$(stat -f %z "$daily_path" 2>/dev/null || stat -c %s "$daily_path")"
echo "backup_db: wrote $daily_path ($size bytes)"
