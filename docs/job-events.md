# Job Events — SSE Contract

Source of truth for the events emitted by `GET /api/jobs/stream`. All clients
(library frontend, cube companion, future CLI) consume from this contract. Any
event-shape change requires a coordinated update across all three consumers.

## Status

DRAFT — locked as part of the B+C-lite ingestion refactor (design doc at
`~/.gstack/projects/Codex/madu-feat-audit-pr-p3-provider-singleton-invalidation-design-20260513-210618.md`).

## Transport

- Endpoint: `GET /api/jobs/stream?after_id={int}` (existing route in `routes/jobs.py`)
- Auth: query param `?token=...` via `withLocalApiToken()` (SSE can't send custom headers from EventSource)
- Format: `text/event-stream`, one event per ingestion job state transition or progress tick
- Cursor: `after_id` is the last `event_id` the client received. On reconnect, client passes its highest-seen id; server replays events with `id > after_id` then resumes live stream
- Reconnect: client uses native `EventSource` reconnect (5s default). Server tolerates duplicate consumers (same token may stream from two windows)

## Coalescing

| Mode | Per-job rate | Aggregate rate |
|---|---|---|
| Fast pass (active for ~30s during initial ingestion) | Max 4 Hz (250 ms between events per job_id) | 1 batch event per second |
| Deep pass (active for ~5 min during quality pass) | Max 1 Hz (1 sec between events per job_id) | 1 batch event per second |
| Idle (no jobs running) | No events | No events |

Coalescing happens server-side in `routes/jobs.py`. Last-write-wins per
`(job_id, stage)` — the latest progress value within a coalescing window
overwrites earlier ones.

## Event types

All events share a base envelope:

```json
{
  "id": 12345,
  "ts": "2026-05-14T00:10:00.123Z",
  "type": "job_progress",
  "job_id": "uuid-string",
  "payload": { ... }
}
```

### `job_created`

Emitted when `enqueue_import()` accepts a new job and writes the row.

```json
{
  "type": "job_created",
  "job_id": "...",
  "payload": {
    "filename": "Biology-Chapter-7.pdf",
    "subject_name": "General",
    "size_bytes": 280123456,
    "kind": "document_import"
  }
}
```

### `job_stage_changed`

Emitted at every stage transition. Stages: `queued`, `extracting_text` (fast
pass), `indexing` (fast pass), `fast_pass_ready`, `deep_pass_extracting`,
`deep_pass_indexing`, `ready`, `failed`, `cancelled`.

```json
{
  "type": "job_stage_changed",
  "job_id": "...",
  "payload": {
    "from_stage": "extracting_text",
    "to_stage": "indexing",
    "progress": 0.4
  }
}
```

### `job_progress`

Coalesced progress within a stage. Progress is `0.0`–`1.0` for the CURRENT
stage, not the whole job.

```json
{
  "type": "job_progress",
  "job_id": "...",
  "payload": {
    "stage": "extracting_text",
    "progress": 0.65,
    "page_current": 130,
    "page_total": 200
  }
}
```

### `job_ready`

Terminal success. Emitted twice in two-pass mode: once as `fast_pass_ready`
(via `job_stage_changed`) and once as the final `ready` event.

```json
{
  "type": "job_ready",
  "job_id": "...",
  "payload": {
    "document_id": "uuid",
    "stage": "ready",
    "duplicate": false,
    "fast_pass_duration_ms": 28456,
    "deep_pass_duration_ms": 287123
  }
}
```

### `job_failed`

Terminal failure. `reason_code` is machine-readable; `reason_text` is for the user.

```json
{
  "type": "job_failed",
  "job_id": "...",
  "payload": {
    "stage": "extracting_text",
    "reason_code": "worker_timeout|worker_oom|worker_crash|disk_full|invalid_pdf|unsupported_type",
    "reason_text": "Extraction worker exceeded 10-minute wall-clock limit and was killed.",
    "retriable": true
  }
}
```

### `batch_progress`

Aggregate event for the cube's overall progress bar. Emitted once per second
when any jobs are active.

```json
{
  "type": "batch_progress",
  "job_id": null,
  "payload": {
    "total_jobs": 25,
    "completed": 8,
    "failed": 0,
    "in_progress": 4,
    "queued": 13,
    "bytes_total": 2147483648,
    "bytes_completed": 687194767
  }
}
```

## Consumer guarantees

- **Idempotency**: every event has a monotonic `id`. Clients SHOULD dedupe by id (handles reconnect replay).
- **Ordering**: events for a single `job_id` arrive in the order they happened. Cross-job ordering is best-effort.
- **Catch-up**: a client that's been offline for N seconds reconnects with `after_id` = last-seen-id and gets all events since.
- **No silent drops**: if a job transitions to `failed`, exactly one `job_failed` event is emitted. Clients can rely on terminal events.

## Failure modes the schema handles

| Scenario | Events emitted |
|---|---|
| Worker OOM (process killed) | `job_failed` with `reason_code: worker_oom`, `retriable: true` |
| Worker hung past wall-clock | `job_failed` with `reason_code: worker_timeout`, `retriable: true` |
| Worker crash (non-zero exit) | `job_failed` with `reason_code: worker_crash`, `retriable: true` |
| Backend restart mid-job | Job resumes via `resume_unfinished_jobs()`; client sees a `job_created` replay (idempotent) and continues |
| User cancels via UI | `job_failed` with `reason_code: user_cancelled`, `retriable: false` |
| Partial extraction (page corruption) | `job_ready` with payload note `"partial": true`, `pages_extracted < pages_total` |

## Frontend integration

### Library view (`useJobsStream.ts` hook)

- Opens `EventSource` on mount, closes on unmount
- Maintains in-memory `jobs` map keyed by `job_id`
- On `job_ready` for a NEW document: triggers `documentsQuery.refetch()`
- On `job_failed`: surfaces toast with `reason_text`
- Reuses `withLocalApiToken()` for auth

### Cube companion (`window.companion.setBatchProgress(...)`)

- Subscribes via the same `EventSource` (singleton; not opened twice per window)
- On `batch_progress`: updates the cube's overall bar
- On `job_stage_changed` to terminal states: triggers cube animation (`encouraging` for ready, `stumped` for failed)

### Backwards compatibility

- The existing `__carrelRefreshLibrary()` hook (wired in `useDocumentsQuery.ts`) stays as a fallback for the `nudgeLibraryRefresh()` Swift code path. SSE supersedes it for new clients but the nudge is harmless if SSE is also active (refetch is idempotent).
- The existing `/api/jobs` and `/api/jobs/events` polling endpoints stay; SSE is additive, not replacing.

## Open questions (defer to v2)

- **Mid-job per-page progress streaming from worker → parent**: workers report progress on done/error today via stdout JSON. Per-page progress requires Unix-socket RPC from worker → parent. Defer until SSE granularity is provably insufficient.
- **Multi-window SSE coordination**: two Carrel windows on the same machine each open their own EventSource. Server doesn't deduplicate. Probably fine; flag if it causes scheduler-event amplification.
