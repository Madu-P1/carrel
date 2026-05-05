#!/usr/bin/env bash
# test_backup_restore_drill.sh — end-to-end smoke test for the backup
# and restore scripts. Exits non-zero if either step fails OR if the
# restored DB doesn't match the source.
#
# Run locally: bash script/test_backup_restore_drill.sh
# Run in CI:   add as a job step (no Python deps, just sqlite3+bzip2).
#
# Drill outcome is the only thing that proves backups work. A backup
# that has never been restored is just bytes on disk.

set -euo pipefail

work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

export CARREL_BASE_DIR="$work"
export CARREL_DB_PATH="$work/data/einstein_tutor.db"
export CARREL_BACKUP_DIR="$work/backups"
# Drill operates on a fresh temp DB — no production uvicorn touches
# this path, so bypass the running-uvicorn safety check.
export CARREL_RESTORE_FORCE=1

mkdir -p "$work/data"

# Seed a DB with known content. The schema doesn't matter — we just
# need bytes to round-trip.
sqlite3 "$CARREL_DB_PATH" <<'SQL'
CREATE TABLE documents (id INTEGER PRIMARY KEY, title TEXT NOT NULL);
INSERT INTO documents (title) VALUES
  ('one'), ('two'), ('three'), ('four'), ('five');
PRAGMA journal_mode=WAL;
SQL

source_count="$(sqlite3 "$CARREL_DB_PATH" 'SELECT COUNT(*) FROM documents;')"
echo "drill: seeded source DB with $source_count rows"

# 1. Backup.
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT_DIR/script/backup_db.sh"

backup_count="$(ls -1 "$CARREL_BACKUP_DIR"/daily/*.db.bz2 | wc -l | tr -d ' ')"
if [[ "$backup_count" -lt 1 ]]; then
  echo "drill: FAIL — backup script produced no files" >&2
  exit 1
fi
echo "drill: backup wrote $backup_count file(s)"

# 2. Mutate the live DB so we know restore actually replaces it.
sqlite3 "$CARREL_DB_PATH" "DELETE FROM documents WHERE id > 2;"
mutated_count="$(sqlite3 "$CARREL_DB_PATH" 'SELECT COUNT(*) FROM documents;')"
if [[ "$mutated_count" != "2" ]]; then
  echo "drill: FAIL — mutate step didn't take, got $mutated_count rows" >&2
  exit 1
fi
echo "drill: mutated live DB to $mutated_count rows (expected restore to undo this)"

# 3. Restore.
"$ROOT_DIR/script/restore_db.sh" latest

restored_count="$(sqlite3 "$CARREL_DB_PATH" 'SELECT COUNT(*) FROM documents;')"
if [[ "$restored_count" != "$source_count" ]]; then
  echo "drill: FAIL — restored count $restored_count != original $source_count" >&2
  exit 1
fi

echo "drill: PASS — restored $restored_count rows from backup"
