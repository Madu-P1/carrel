# Discovered blockers (autonomous run, 2026-05-07)

## B1 — Stale local-token after app restart

**Symptom:** After `bash script/build_and_run.sh run`, the Library subject grid renders skeletons indefinitely. Backend log shows `GET /api/documents → 403 Forbidden` repeatedly.

**Root cause hypothesis:** the in-memory local-API token rotates on every backend restart (`services/local_api_security.py`). The frontend caches the token from a previous session in `localStorage` (or wherever) and keeps sending the stale value.

**Where to look:** the token-fetch path. There's a `GET /api/local-token` call early in the boot, but if it succeeds and yields a NEW token, the frontend's cached value should update; if it doesn't, that's the bug. Check `services/api/endpoints.ts` or the auth wrapper for where the token is read/written.

**Workaround:** unknown. Current data shows even fresh requests hit 403, suggesting the cached token is being preferred over a freshly fetched one.

**Severity:** medium. Doesn't prevent ingestion (uploads work via direct curl + correct header). Does prevent the user from seeing what they uploaded in the Library grid until manually fixed.

**Not investigating further this turn:** out of scope for the Word/Excel viewer thread. Flag for the morning brief.

## B2 — SubjectCardGrid rendering bug (related to B1)

The grid stays in skeleton state. Almost certainly downstream of B1; once /api/documents stops 403'ing, the grid likely populates. Verify after fixing B1.
