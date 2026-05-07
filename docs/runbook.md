# Runbook

Operational playbook for Carrel. Each section answers a single
question: "what do I run when X breaks?"

## Demo readiness check (run before any investor / design-partner demo)

```bash
bash script/demo-readiness.sh
```

Hits 8 endpoints against the running backend and reports pass/fail
per gate. Catches the failure modes the autonomous overnight runs
hit at least once each:

- Backend reachable
- Local-API token resolves (catches the stale-cache bug)
- /api/documents returns 200 with auth header
- /api/plan returns events + suggestions
- /api/plan/deadlines surfaces detector output
- First document's detail loads with chunks (citation flight needs both)
- Calendar feeds present (else Plan view shows empty-state CTA)
- SRS pipeline live

Exit codes: 0 = all green, demo confidently. 1 = at least one check
failed, fix before going live. 2 = backend unreachable.

The script is non-destructive — it only reads. Safe to run mid-demo
in a side terminal.

## Backups

### What gets backed up
- `~/Library/Application Support/Carrel/data/einstein_tutor.db`
- That's everything user-facing: documents, notes, embeddings, plan,
  calendar, sessions, mastery state. The frontend dist and the macOS
  bundle are reproducible from git.

### Manual backup (right now)
```bash
script/backup_db.sh
# Writes to ~/Library/Application Support/Carrel/backups/daily/
# Keeps 14 daily + 8 weekly compressed snapshots.
```

### Scheduled nightly backup (recommended)
Drop this file at `~/Library/LaunchAgents/com.madu.carrel.backup.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.madu.carrel.backup</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>/ABSOLUTE/PATH/TO/Codex/script/backup_db.sh</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>3</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardErrorPath</key>
  <string>/tmp/carrel-backup.err</string>
  <key>StandardOutPath</key>
  <string>/tmp/carrel-backup.log</string>
</dict></plist>
```

Then load it:
```bash
launchctl load ~/Library/LaunchAgents/com.madu.carrel.backup.plist
launchctl start com.madu.carrel.backup  # run once now to verify
```

### Restore
```bash
# 1. Quit Carrel completely (Cmd-Q in the app, then verify uvicorn
#    isn't running):
pgrep -fl "uvicorn main:app" && echo "still running"

# 2. Restore. `latest` picks the newest daily snapshot:
script/restore_db.sh latest

# Or by file:
script/restore_db.sh ~/Library/Application\ Support/Carrel/backups/daily/einstein_tutor-20260101-030000.db.bz2

# 3. The previous DB is moved aside as
#    einstein_tutor.db.pre-restore-<ts>. Delete after verifying.

# 4. Relaunch Carrel.
```

### Disaster recovery drill
End-to-end automated test, runs in CI on every push:
```bash
bash script/test_backup_restore_drill.sh
# Round-trips a synthetic DB through backup + restore and exits 0
# only if the restored row count matches the original.
```

## Common operational issues

### "Backend won't start" (Carrel.app shows a connection error)

1. Tail the supervisor log:
   ```bash
   tail -f dist/einstein-backend.log
   ```
2. Look for `address already in use` (port 8000 collision):
   ```bash
   lsof -nP -iTCP:8000 -sTCP:LISTEN
   # Kill the squatter, then relaunch Carrel.
   ```
3. Look for `ImportError`/`ModuleNotFoundError` (venv drifted from
   requirements.lock):
   ```bash
   .venv/bin/pip install -r requirements.lock
   ```

### "Backend running, frontend can't reach it"
- Verify health: `curl http://127.0.0.1:8000/api/health`
- If 200 but the WebView shows "Reconnecting...", the supervisor
  re-spawned uvicorn but the WKWebView cached a network failure.
  Cmd-R in the app, or quit + relaunch.

### "Calendar events aren't syncing"
- macOS hides the calendars permission silently if the entitlement
  is missing. Confirm:
  ```bash
  codesign -d --entitlements - dist/EinsteinDesktop.app | grep calendars
  ```
  Should print `<key>com.apple.security.personal-information.calendars</key><true/>`.
- Reset the prompt: System Settings → Privacy & Security → Calendars,
  toggle Carrel off + on.

### "Database disk image is malformed"
- Almost always the WAL/SHM siblings drifted from the main DB. After
  any external file copy of the DB, also copy `*-wal` and `*-shm`,
  or delete them so SQLite recreates.
- The restore script handles this; manual recovery:
  ```bash
  cd ~/Library/Application\ Support/Carrel/data
  sqlite3 einstein_tutor.db ".recover" > recovered.sql
  mv einstein_tutor.db einstein_tutor.db.broken
  sqlite3 einstein_tutor.db < recovered.sql
  ```

## Observability

- Structured JSON logs: `~/Library/Application Support/Carrel/logs/einstein-backend.jsonl`
- Per-request id is in the `request_id` field (matches `X-Request-ID`
  header echoed in responses).
- Live metrics snapshot:
  ```bash
  curl -s http://127.0.0.1:8000/api/metrics | jq .
  ```
- Sentry: set `SENTRY_DSN=<dsn>` in env, restart. SDK is in
  `requirements-dev.lock` only — install on the host that runs the
  backend with `pip install sentry-sdk[fastapi]`.

## Releasing

See `CHANGELOG.md` for the version history and the release process.
