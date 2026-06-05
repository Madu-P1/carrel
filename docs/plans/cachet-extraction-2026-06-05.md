# Cachet extraction plan: strangle Carrel in place

- Date: 2026-06-05
- Governs: [ADR-0011](../adr/ADR-0011-extract-cachet-strangle-carrel.md)
- Premise (operator-confirmed 2026-06-05): Carrel-the-study-app is dead, Cachet
  is the sole future product, one consumer of this codebase.
- Goal: a permanent, clean separation that preserves the hardened verification
  engine perfectly and reaches a verification-first Cachet codebase, executed as
  small reversible steps up to two clearly-marked one-way doors.

## Operating rules (apply to every phase)

1. **Characterization net first.** No deletion or move proceeds until the verify
   path's observable behavior is pinned by tests. The net is what makes every
   step below safe.
2. **One coherent slice per PR.** Each PR does one thing and is independently
   revertable. No mixed refactor-plus-delete diffs (tidy-first, separate
   commits).
3. **Grep before you delete.** Before removing any module, grep for inbound
   imports from the KEEP set. Delete only when nothing in the verify path
   references it.
4. **Verify-green after each slice.** Run the full verify chain (not the fast
   pre-commit subset) and the verify/legal test suites after every PR. Green to
   proceed; red means revert the one slice and narrow it.
5. **Reversible until P4.** P0-P3 ship behind nothing irreversible. P4 (drop
   tables) and P5 (rename/identity) are the only one-way doors and do not start
   until a standalone Cachet runs green.

The verify chain to run after each slice: `script/generate-api-types.sh`, the
frontend typecheck/lint/test/build, `ruff check` + `ruff format --check`, and
the verify-relevant Python suites: `tests.test_verify`, `tests.test_verify_stream`,
`tests.test_quote_check`, `tests.test_align`, `tests.test_legal_case_verification`,
`tests.test_legal_courtlistener`, plus `tests.test_briefs` / `tests.test_briefs_routes`.

## The seam (the only new design)

Introduce one narrow, deep interface and route verify through it. This is the
branch-by-abstraction lever that decouples verify from the study framing.

```
# services/grounding.py (new, thin)
GroundingEnvelope = { claims, unsupported_spans, citations, provider, model, error }

def ground(draft, sources, *, on_event=None) -> GroundingEnvelope: ...
def ground_stream(draft, sources) -> Iterator[GroundingEvent]: ...
```

`ground` and `ground_stream` wrap the existing
`services.tutor.grounded_tutor_envelope` (services/verify.py:251) and
`grounded_tutor_envelope_steps` (services/verify.py:610). No behavior change;
this is a pure interposition. After P1, `services/verify.py` imports
`services.grounding`, never `services.tutor` directly, and `tutor.py` is an
implementation detail that can be specialized or shrunk later without touching
the verify surface.

---

## P0: Pin the behavior (REVERSIBLE)

**Goal:** a characterization net over verify so no later deletion can silently
change behavior.

**Steps:**
- Audit existing coverage: `tests/test_verify.py`, `test_verify_stream.py`,
  `test_quote_check.py`, `test_align.py`, `test_legal_case_verification.py`,
  `test_legal_courtlistener.py`, `test_briefs*.py` already exist.
- Add a characterization test asserting the `grounding` envelope contract that
  `services/verify.py` consumes: given a fixed draft + fixed source pool, the
  `{claims, unsupported_spans, citations, provider}` shape and the per-claim
  verdict mapping are stable. Pin current output, including edge cases (empty
  draft, no sources, a seeded-wrong citation, a verbatim-quote miss).

**Gate (done when):** the net captures verify's observable behavior end to end,
including one seeded-bad-citation case and one bad-quote case, and is green on
the current build.

**Rollback:** N/A (additive tests only).

---

## P1: Define the seam (REVERSIBLE)

**Goal:** verify depends on `services.grounding`, not on `services.tutor`
internals.

**Steps:**
- Add `services/grounding.py` wrapping the two `grounded_tutor_envelope*`
  entry points.
- Change `services/verify.py` to call `grounding.ground` / `ground_stream`.
- Leave `services/tutor.py` unchanged behind the seam.

**Gate (done when):** `grep -n "tutor" services/verify.py` shows no direct tutor
import; the P0 net is green; verify output byte-identical to pre-P1.

**Rollback:** revert the single PR; the seam is one file plus one import swap.

---

## P2: Stand up Cachet-only end to end (REVERSIBLE, the skeleton)

**Goal:** a standalone Cachet that runs with only verify + briefs + the minimal
ingest/retrieval substrate, everything else dormant behind a flag. This proves
the seam holds before any deletion.

**Steps:**
- Backend: a `CACHET_ONLY` composition in `main.py` (or a `serve-cachet`
  entry) that registers only `routes/verify.py`, `routes/briefs.py`, and the
  minimal `routes/documents.py` ingest path the verify corpus needs. Keep the
  local-API token gate and CORS (the host trust boundary) intact; factor them
  into a small `local_security` middleware the Cachet composition reuses.
- Bring the Option A standalone Cachet frontend and `serve-cachet.py` from their
  branch onto this line of development (per ADR-0011 open question 4).
- Frontend: a Cachet entry that imports only `features/verify/*` and
  `features/shelf/*`, with a verify-only `AppShell` sidebar (drop the
  library/study/ask/concepts/plan sidebar sections).

**Gate (done when):** with `CACHET_ONLY` on, a user can ingest a source
document, run verify (live and streamed), see disposition cards, and save/load a
brief, with every study/learning route and view absent from the running app and
the bundle. The full study app still builds with the flag off (nothing deleted
yet).

**Rollback:** the flag. Off restores the full app exactly.

---

## P3: Strangle the baggage (REVERSIBLE per slice)

**Goal:** delete the study app, one leaf-first slice per PR, verify-green after
each.

**Method per slice:** grep for inbound imports from the KEEP set; if clean,
delete the frontend feature, then its route, then its service, then its tests;
run the verify chain; green commits the slice as its own PR; red reverts and
narrows.

**Suggested slice order (leaf-first, least-coupled first):**

| # | Slice | Delete (paths) |
|---|---|---|
| 1 | Dashboard / onboarding / exports | `routes/dashboard.py`, `services/dashboard.py`, `routes/onboarding.py`, `routes/exports.py`, `frontend/src/features/dashboard/` |
| 2 | Artifact studio / synthesis / evidence | `routes/studio.py`, `routes/synthesis.py`, `routes/evidence.py`, `services/artifact_studio.py`, `services/artifact_prompts.py`, `services/orchestrator.py` |
| 3 | Calendar / coach / plan | `routes/plan.py`, `routes/calendar.py`, `services/calendar/`, `frontend/src/features/plan/` |
| 4 | Concepts / dialogue | `routes/concepts.py`, `services/dialogue.py`, `services/session_engine.py`, `frontend/src/features/concepts/`, `frontend/src/features/session/` |
| 5 | Study / SRS | `routes/study.py`, `services/study.py`, `services/review_scheduler.py`, `frontend/src/features/study/` |
| 6 | Reader / library / notes | `routes/reader_nodes.py`, `services/note_folders.py`, `frontend/src/features/reader/`, `frontend/src/features/library/`, `frontend/src/features/notes/` |
| 7 | Ask / search (UI) | `routes/ask_cards.py`, `routes/search.py`, `frontend/src/features/ask/`, `frontend/src/features/search/` (keep `services/retrieval/*`) |
| 8 | Tutor route (NOT the engine) | `routes/tutor.py` only. Keep `services/tutor.py` behind the grounding seam. |

**KEEP (the Cachet substrate, never delete in P3):** `routes/verify.py`,
`routes/briefs.py`, `routes/documents.py` (minimal ingest), `services/verify.py`,
`services/briefs.py`, `services/legal/*`, `services/tutor.py` (behind the seam),
`services/grounding.py`, `services/retrieval/*`, `services/ingestion*`,
`services/extraction/text_artifacts.py`, `services/helpers.py`, `ai/router.py`,
`ai/providers.py`, `ai/prompt_sanitization.py`, `db.py`, `api_models.py`
(verify + briefs + shared subset), `app_logging.py`, the local-API security
middleware, and the frontend `features/verify`, `features/shelf`,
`design-system/*`, `services/api/*`, `app/shell/*` (slimmed),
`features/shared/ProviderQualityGateBanner`.

**DECIDE during the slice (resolve by grep, do not guess):**
- `routes/documents.py` + `services/ingestion/*`: KEEP, verify needs an ingested
  source pool. Slim to the ingest path verify actually exercises.
- `services/app_state.py` `log_study_event` / `fetch_recent_events`: these are
  passed as callbacks into `verify_draft` and `grounded_tutor_envelope`. If they
  carry only study telemetry, replace with no-op stubs rather than deleting the
  parameter (avoid a signature change rippling into the engine). Confirm by grep.
- `services/jobs.py`: KEEP only if the kept ingest path uses it.

**Gate (done when):** all eight slices merged, the running app exposes only
verify/briefs/documents routes and verify/shelf views, and the full verify chain
is green.

**Rollback:** any slice reverts independently; merged slices revert by `git
revert` until P5.

---

## P4: Collapse the schema (ONE-WAY DOOR, data-destructive on dead tables)

**Goal:** a lean Cachet schema, without rewriting history.

**Steps:**
- Do NOT edit `migrations/0001_initial.sql`. Add a new forward migration
  `migrations/00NN_drop_study_tables.sql` that drops the tables P3 orphaned.
- Candidate drop set (confirm each is unreferenced by the verify path first):
  `srs_cards` (and `0017`/`0018`/`0022` follow-ons), `concepts`, `concept_edges`,
  `dialogue_sessions`, the `0009` calendar/planning tables, `study_events`,
  `notes`, `note_folders` (`0023`), and `tutor_exchanges` (ADR-0011 open
  question; confirm verify does not read it).
- KEEP: `documents`, `chunks` (`0006` FTS5), `chunks_vec` (`0007`), typed
  `nodes` / `node_fts` / `node_embeddings` (`0016`), `briefs` (`0024`).

**Gate (done when):** the migration applies cleanly on a fresh DB and on a
copy of a populated DB, verify chain green, and `db.py::apply_migrations`
produces a schema with only the KEEP tables plus the legal/briefs tables.

**Rollback:** restore from the pre-migration DB backup. Because this drops data
on dead tables, take a backup first and treat it as irreversible in practice.
This is why it is gated behind a green standalone Cachet.

---

## P5: Cut the identity (ONE-WAY DOOR, checkpoint first)

**Goal:** this repository is Cachet, not Carrel-with-a-verify-tab.

**Steps:**
- Execute the deferred rename from `docs/notes/2026-04-29-carrel-rename.md`:
  the `com.madu.EinsteinDesktop` bundle, `EinsteinDesktop.app`,
  `data/einstein_tutor.db`, and the internal einstein/carrel identifiers, to
  cachet equivalents.
- Make Cachet the default: drop the `CACHET_ONLY` flag (Cachet is the app now),
  point the macOS WKWebView host at the Cachet build.
- Update `CLAUDE.md`, `HANDOFF.md`, and `AUTONOMOUS_WORK_PLAN.md` to the Cachet
  framing; mark the study surface as removed, not paused.

**Gate (done when):** a clean checkout builds, launches, and verifies under the
Cachet identity with no einstein/carrel identifiers remaining in shipped code,
and the verify chain is green.

**Rollback:** none in practice. This is the irreversible commit. Take a session
checkpoint and confirm P0-P4 are fully green before starting.

---

## Risks and mitigations

- **A deletion silently breaks verify.** Mitigated by the P0 net + grep-gate +
  verify-green-per-slice. If a slice goes red, the one slice reverts.
- **The grounding engine carries a hidden study dependency.** Surfaced by P1
  (the seam makes every engine input explicit) and by the grep-gate in P3.
- **`app_state` callbacks are load-bearing for verify.** Mitigated by stubbing
  rather than removing the parameter (no engine signature change).
- **Schema drop hits a still-referenced table.** Mitigated by confirming each
  table unreferenced before P4 and by the pre-migration backup.
- **Branch divergence (Option A frontend / serve-cachet on another branch).**
  Resolved in P2 by bringing them onto this line before the strangler starts.

## What NOT to do (from ADR-0011)

- No fresh-repo-plus-port (rewrite trap, re-ports the hardened engine blind).
- No big-bang. Every phase ships and reverts on its own.
- No shared substrate library (one consumer, YAGNI, wrong abstraction).
- No touching the legal engine or the deterministic verify core during the move.
- No rewriting `migrations/0001`; drop by forward migration only.
- No Electron until a real packaging requirement forces it.

## Definition of done

The repository builds, launches, and verifies under the Cachet identity; only
the verification surface (verify, briefs, the minimal ingest/retrieval/grounding
substrate, the legal engine) remains; the schema holds only the KEEP tables; the
verify chain is green; no einstein/carrel identifiers remain in shipped code.
The verification engine's behavior is byte-identical to its pre-extraction
behavior, proven by the P0 characterization net.
