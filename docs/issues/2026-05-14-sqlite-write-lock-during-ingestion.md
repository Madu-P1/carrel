# 2026-05-14 — SQLite write-lock contention during ingestion

## Summary

User reported "the library crashed" when uploading a large 266 MB Biology
PDF. Investigation found NO process crashes (no entries in
`~/Library/Logs/DiagnosticReports/EinsteinDesktop*` or
`com.apple.WebKit.WebContent*`). The actual failure surfaced in
`dist/einstein-backend.log` as:

```
ERROR:    Exception in ASGI application
  ...
  File "services/tutor.py", line 1228, in grounded_tutor_envelope
    log_study_event(...)
  File "services/app_state.py", line 48, in log_study_event
    conn.execute(...)
sqlite3.OperationalError: database is locked
INFO:     127.0.0.1:64584 - "POST /api/tutor/query HTTP/1.1" 500 Internal Server Error
```

The user's tutor query returned 500 because `log_study_event()` couldn't
acquire the SQLite writer lock. The user perceived this as "the library
crashed" because they were on the Library page when the tutor errored out.

## Root cause

SQLite allows ONE writer at a time. When ingestion is mid-flight on a large
PDF, `_run_import_job()` in `services/jobs.py` holds long write transactions
(chunk inserts, vector index inserts, concept upserts). Concurrent writes
from request-path code — like `log_study_event()` in `services/app_state.py:48`
— block on `busy_timeout`, then raise `OperationalError: database is locked`.

WAL mode + busy_timeout (already configured per PR-S5 — commit `b6f546c2`)
helps but does not eliminate this. WAL allows concurrent READS during
writes, but writes still serialize. A multi-second chunk-insert transaction
will block any other writer for the duration.

## What this means for the B+C-lite design doc

The design doc claimed the in-process OOM crash would be eliminated "by
construction" once subprocess workers + page-streaming ship. **That claim
is partially wrong for this specific incident.**

- The OOM hypothesis is REFUTED for the user's reported incident (no
  process crashed).
- B+C-lite's process isolation DOES eliminate worker OOM crashes for
  truly huge PDFs (the >2 GB case the user worries about).
- B+C-lite does NOT eliminate write-lock contention. Even with subprocess
  workers, the parent process still does the chunk-insert SQLite writes
  per Issue 1.1B (paths-only IPC, parent reads worker output and writes
  the DB). Long chunk-insert transactions in the parent will continue to
  block tutor queries that try to write `study_events`.

## Three short fixes that ship faster than B+C-lite

These can land independently and reduce user-visible 500s today:

1. **Make `log_study_event()` non-blocking from the request hot path.**
   Wrap it in `asyncio.create_task()` so the user's tutor response
   doesn't block on the telemetry write. Telemetry failure becomes a
   logged warning instead of a 500. ~10 LoC in `services/tutor.py`.

2. **Wrap `log_study_event()` in try/except.** Even simpler: catch
   `sqlite3.OperationalError` and log+swallow. Telemetry is fire-and-forget
   by definition; it should never break user-visible features. ~5 LoC.

3. **Batch chunk inserts in smaller transactions.** Instead of one
   transaction per document (which can be multi-second on a 200-page PDF),
   commit every N chunks (e.g. 100). Each commit releases the writer
   lock, giving other writers a chance. Larger refactor (~30 LoC) but
   addresses the root cause.

Ship 1+2 today (15 min total). Schedule 3 as part of B+C-lite Lane A.

## What B+C-lite should add to address this properly

In Lane A's `_run_import_job` refactor, add an explicit "chunk-write
coordinator" that:

- Commits chunk batches in groups of 100 (configurable).
- Yields control between batches via `await asyncio.sleep(0)` so the
  asyncio event loop services other requests/writes.
- Tracks per-batch wall-clock time; if a batch takes >500 ms, log a
  warning so we know contention is happening.

Add this to the design doc as a 13th locked decision: "Chunk-write
coordination — bounded transaction size + asyncio yield between batches."

## Evidence trail

- User's screenshot showed CoverLetter + School_leaving_Certificate at
  100% ready, then dropped Biology-OP_xQoZM8Z-8.pdf. With 100 MB cap
  the file was rejected (413, no ingestion attempted). After bumping to
  500 MB the user's tutor query (separate flow) crashed with
  `database is locked`.
- `grep "database is locked" dist/einstein-backend.log` shows the
  exception is recurring, not a one-off.
- No matching crash in DiagnosticReports/ → no process actually died.
- Backend stayed alive (subsequent `/api/health` and `/api/jobs` calls
  succeeded).

## Recommended action

1. Land the three short fixes above as a small commit on
   `feat/audit-pr-p3-provider-singleton-invalidation` before B+C-lite work.
2. Update the B+C-lite design doc's premise statement to acknowledge the
   investigation finding and add chunk-write coordination as a locked
   decision.
3. Add a regression test: simulate concurrent ingestion + tutor query,
   assert tutor query does not 500.
