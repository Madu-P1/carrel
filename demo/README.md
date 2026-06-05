# Cachet demo: run of show

A pre-vetted corpus where the catch genuinely fires, verified by the real engine
in `tests/test_demo_corpus.py`. No staging: the refusals below are produced by
the deterministic engine, not scripted.

## Setup (the night before, on the demo machine)

- `CACHET_DETERMINISTIC_VERIFY=1` and `CACHET_LOCAL_CASELAW=1` (no-LLM, offline).
- `COURTLISTENER_API_TOKEN=local` (sentinel; the bundled SQLite answers locally).
- `CACHET_REQUIRE_SQLITE_VEC=1` (fail loud if sqlite-vec is missing).
- Embedder pre-cached via `CARREL_FASTEMBED_CACHE_DIR` (so airplane mode works).
- Ingest `demo/contract-msa.md` once so its clauses are in the `nodes` table.
- Staple the notarization ticket; launch once online, then go to airplane mode.

## Beat 1 — litigator opener (offline, sub-second)

Paste `demo/litigator-motion.md`.

- `Brown v. Board of Education, 347 U.S. 483` resolves from the bundled corpus:
  the case exists. (Honest note: existence is verified; whether the opinion
  supports the proposition is the assistive holding-match tier, off by default.)
- `Marbury v. Carcosa, 999 U.S. 999` does not exist: **Citation not found** (the
  catch), produced by a local lookup with the network monitor flat.

## Beat 2 — the pivot

"Cite-checking is table stakes. Here is the part a cloud tool structurally
cannot do."

## Beat 3 — contract close (the confidential document never leaves the machine)

Load `demo/contract-msa.md`, paste `demo/contract-ai-summary.md`.

- "capped at $1,000,000" vs the contract's $500,000: **parametric contradiction**
  (pure arithmetic, zero ML).
- "two (2) years" matches the contract's term: **present** ("review the full
  clause for context").
- "best efforts" carries no checkable anchor: the honest **could not check**, not
  a silent pass and not an accusation.

## Beat 4 — the audit artifact

Open the Certification Exhibit: timestamp, draft SHA-256, per-source SHA-256, the
named "No data left this device" attestation, the on-device provenance badge,
flagged-items-first. Save as PDF and as JSON.

## Airplane-mode proof

Airplane mode on, network monitor projected and flat for the whole run. The
zero-egress guarantee is also a CI test (`tests/test_zero_egress.py`): both
surfaces run with real sockets forbidden. State honestly that this is behavioral
proof today; the structural split-shell proof is roadmap.

## Honest gaps (do not show these as working)

- Altered-quote detection in the litigator path (quoted run vs opinion text) is
  not wired in the deterministic engine yet; the opener demonstrates the
  fabricated-cite catch, not the altered-quote catch.
- Screenshots at 1440 and 1920 and the full `CLAUDE.md` verify chain (macOS
  build, swift test, evals, benchmarks) run on the demo machine, not in this
  worktree.
