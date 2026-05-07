# Blockers (autonomous run, 2026-05-07)

## ~~B1 — Stale local-token after app restart~~ RESOLVED 2026-05-07

**Symptom:** After `bash script/build_and_run.sh run`, Library subject grid renders skeletons indefinitely; backend log shows `GET /api/documents → 403`.

**Root cause:** `frontend/src/services/api/client.ts` cached the local-API token in a module-level `cachedLocalApiToken` variable. The token regenerates on every backend startup but the frontend never re-fetched. Stale cache → 403 forever, no retry path.

**Fix:** wrapped `api()` in a recursion-guarded `apiInner(path, init, alreadyRetriedAfter403)`. On 403 with a cached token present, clear the cache and recurse once. Lands in commit on the post-Wave-5 series.

**Verification:** backend log after relaunch shows `GET /api/documents → 200 OK` consistently.

## ~~B2 — Library SubjectCardGrid skeleton stuck~~ RESOLVED 2026-05-07

Downstream of B1; resolved by the same fix.
