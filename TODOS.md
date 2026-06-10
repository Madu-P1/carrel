# Carrel — Deferred Work Backlog

Plans that came out of completed reviews but were intentionally not in scope of the milestone they were surfaced in. Each item lives at the path noted; this file is the index.

## Active backlog (from `docs/plans/flashcards-focus-2026-05-09.md` autoplan, approved 2026-05-10)

| Plan | Trigger | Why deferred | Source |
|---|---|---|---|
| `paid-tier-infrastructure.md` | PR 0 split surfaced in eng review | Carrel has no users/accounts/licenses table, no auth middleware, no Stripe. The full "BYOK + paid gate" story is multi-week work that should be its own milestone, not an appendix to flashcards. Includes macOS Keychain integration for Anthropic key storage. | autoplan Phase 3 |
| `flashcard-quality-investigation.md` | User feedback ("card quality is bad") | Auto-gen is paused via PR 0a until card quality is investigated. Needs prompt-engineering pass + eval suite expansion before auto-gen can return behind a feature flag. | autoplan Phase 1 (CEO) |
| `voice-refresh-app-wide.md` | User directive ("more welcoming") | Flashcard surface gets voice work in this milestone (deferred to week 3 pending telemetry). Library, Reader, Ask, Plan, Dashboard, Session need their own focused voice pass. | autoplan Phase 2 (Design) |
| `bulk-card-generation-flow.md` | CEO subagent's "generation-first" reframe | If post-PR-7 telemetry shows median active user has <20 cards, the real funnel issue is generation, not review. This plan covers "drop a textbook chapter → 50 cards proposed in 30s, all source-linked → accept-all in one click." | autoplan Phase 1 (CEO) |
| ~~`flashcards-citation-on-back.md`~~ | ~~Original PR 4~~ | **SHIPPED 2026-05-12** as PR 4 of flashcards-focus. | autoplan Phase 3 |
| ~~`flashcards-cloze-and-reverse.md`~~ | ~~Original PR 5~~ | **SHIPPED 2026-05-13** as PR 5.1 (cloze, ADR 0002) and PR 5.2 (reverse-pair, ADR 0003) of flashcards-focus. | autoplan Phase 3 |

## Active backlog (from `~/.gstack/projects/Codex/madu-feat-audit-pr-p3-provider-singleton-invalidation-design-20260513-210618.md` ingestion-robustness eng review, approved 2026-05-14)

| Plan | Trigger | Why deferred | Source |
|---|---|---|---|
| `afm-ingestion-compatibility.md` | Eng review of B+C-lite ingestion plan | When AFM lands (per `docs/plans/afm-integration-2026-05-10.md`, ACTIVE), verify the new subprocess workers + two-pass ingestion play nicely with `EinsteinAFMBridge`. AFM is a separate Swift sidecar with its own resource footprint; `MemoryPressure.is_safe_to_start_worker()` and adaptive concurrency must account for AFM holding memory. Risk: extraction worker spawns at the same time AFM is loading a model → unified-memory thrash. Acceptance: ingestion + AFM concurrent on a 16GB Mac without page-fault storms. | plan-eng-review 2026-05-14 |
| `auto-snapshot-before-bulk-batch.md` | Eng review of B+C-lite ingestion plan | A 25-file batch that fails halfway leaves cards/concepts/chunks in inconsistent rows. `chunk_locks` is gone (cards anchor to source spans now), but partial ingestion can still leave orphaned vector entries or half-indexed concepts. Auto-snapshot the SQLite DB before any batch >5 files; expose a one-click revert in the cube companion error UI. Reuses the existing `pg_dump`-equivalent SQLite `.backup` mechanism. Acceptance: dropped batch fails → user can restore pre-batch state in <5s. | plan-eng-review 2026-05-14 |
| `cross-platform-memory-pressure-fallback.md` | Eng review of B+C-lite ingestion plan | When Carrel ports to Linux (no immediate plan), `MemoryPressure.is_safe_to_start_worker()` needs a psutil-based fallback for the macOS-specific `vm_stat` + `sysctl vm.swapusage` calls. The helper is wrapped exactly so this fallback is a 1-day swap, but capture it now or the macOS-only assumption will calcify. | plan-eng-review 2026-05-14 |

## Active backlog (from structural-citation gate, Gate 0 shipped 2026-05-22)

| Plan | Trigger | Why deferred | Source |
|---|---|---|---|
| Gate 1 — low-information body + chunks-path heading filter | Gate 0 closed the structural-citation hole on the typed-node path only | The legacy chunks path is structurally untyped, so a heading line inside a chunk window cannot be caught by a `node_type` check — it needs a heuristic (length, finite-verb presence, bare-reference detection). The same heuristic catches `body` nodes that are themselves not answer-bearing (page numbers mis-typed as body, fragments). Deterministic, no model. | `docs/notes/2026-05-22-structural-citation-gate.md` |
| Gate 2 — semantic entailment verifier (Selene Mini) | Gate 0/1 are structural; nothing checks whether a verbatim, answer-bearing citation actually supports its claim | A citation can be verbatim and answer-bearing yet still not entail the claim it is attached to. This needs an LLM-as-a-judge. Candidate: Atla Selene-1-Mini (8B open-weights) run locally via Ollama as a judge role distinct from the answering model. Land in the eval harness first (offline, parallel scorer) before any answer-time use. | `docs/notes/2026-05-22-structural-citation-gate.md` |

## Active backlog (Cachet source-viewer, queued 2026-06-07)

| Plan | Trigger | Why deferred | Source |
|---|---|---|---|
| ~~Cachet `SourceView` (reader recycled for verification)~~ | ~~Operator wants Cachet users to open a saved brief and view its sources at the exact verified span~~ | **SUPERSEDED 2026-06-11** by the Document Examination drawer (PR #167): `frontend/src/cachet/examine/` renders the ORIGINAL PDF/DOCX in place with honest quote anchoring (no match → visible refusal), wired into SourceInspector / Lectern / Vault. No `/source` route or reader recycling needed. **The P3 note survives:** `reader_nodes` stays KEEP for the SourcePassageOverlay resolve path; extract render primitives before deleting `features/reader`. | `docs/notes/2026-06-07-cachet-source-viewer.md` |

## Notes
- Each plan name in `docs/plans/<plan>.md` when written.
- Pre-commit kill conditions and success metrics live in the originating plan, not here.
- Re-prioritize this list after every milestone closeout, not continuously.
