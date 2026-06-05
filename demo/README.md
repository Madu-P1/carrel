# Cachet demo: run of show

A pre-vetted corpus where the catch genuinely fires, verified by the real engine
in `tests/test_demo_corpus.py`. No staging: the refusals below are produced by
the deterministic engine, not scripted.

## Setup (the night before, on the demo machine)

- `CACHET_DETERMINISTIC_VERIFY=1` (no-LLM deterministic engine). PREFLIGHT, the
  single most important check: assert this is exported in the SERVING process, not
  just your shell. If it is unset, the stream endpoint the UI calls falls through to
  the LLM + CourtListener path, which egresses the draft (silently, if an
  `ANTHROPIC_API_KEY` is present). Fail the demo launch loud if the flag is unset.
- `COURTLISTENER_API_TOKEN=local` (sentinel; the bundled SQLite answers locally).
- `CACHET_REQUIRE_SQLITE_VEC=1` (fail loud if sqlite-vec is missing).
- Embedder pre-cached via `CARREL_FASTEMBED_CACHE_DIR` (MANDATORY: the contract
  close needs the local embedding weights; with the deterministic flag on, a cold
  cache fails LOUD with an offline error rather than downloading, so Beat 3 would
  show an error banner instead of the contradiction. Warm the cache once online).
- Ingest **only** `demo/contract-msa.md` so its clauses are in the `nodes` table.
  The contract close scopes to every `ready` document, so a stray leftover ready
  doc from a dry-run would join the comparison and could surface the wrong clause.
  Confirm exactly one ready document before the demo.
- Staple the notarization ticket; launch once online, then go to airplane mode.

## Beat 1 — litigator opener (offline, sub-second)

Paste `demo/litigator-motion.md`. Three checks fire, all offline:

- `Brown v. Board of Education, 347 U.S. 483` resolves from the bundled corpus:
  the case exists, and the verbatim quote ("Separate educational facilities are
  inherently unequal") matches the bundled opinion text. (Honest note: existence
  and the quote are verified; whether the opinion supports the broader proposition
  is the assistive holding-match tier, off by default.)
- The next sentence cites the same case but misquotes it as "separate facilities
  are inherently equal". The engine does not have the full opinion bundled, so
  instead of guessing it **REFUSES**: "Could not verify this quotation against the
  available opinion text." Narrate this as the refusal, not as an accusation: the
  tool will not call a quote fabricated unless it can prove it, and it never does
  here. (To turn this into a hard "altered quote caught", bundle the full Brown
  opinion; that is a roadmap step, not today's behavior.)
- `Marbury v. Carcosa, 999 U.S. 999` does not exist: **Citation not found** (the
  fabricated-cite catch), produced by a local lookup with the network monitor flat.

## Beat 2 — the pivot

"Cite-checking is table stakes. Here is the part a cloud tool structurally
cannot do."

## Beat 3 — contract close (the confidential document never leaves the machine)

Load `demo/contract-msa.md`, paste `demo/contract-ai-summary.md`. Each verdict
names the clause and quotes both values, so the record stands on its own:

- "executed on March 11, 2024" vs the contract's March 11, 2023:
  **contradiction** ("The summary states March 11, 2024; Section 1 states
  March 11, 2023").
- "capped at $1,000,000" vs the contract's $500,000: **contradiction** ("The
  summary states $1,000,000; Section 8 states $500,000"), pure arithmetic, zero
  ML.
- "two (2) years" matches the contract's term: **present** in Section 12
  ("review the full clause for context").
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

## Honest scope (state plainly, do not oversell)

- The quote check confirms a quote that is verbatim in the bundled opinion and
  REFUSES (could-not-check) when it is not, because the bundled opinion is not
  guaranteed complete. It never calls a quote "altered/fabricated". Attribution is
  same-sentence only, and a quote from a non-cited source is never checked. No
  false accusations, by design.
- Caption matching auto-flags a clearly-different caption (no shared party token,
  or a near-equal collision) and surfaces the resolved case name on every cite, so
  the attorney can compare it to the draft's parties. It does NOT claim to catch a
  fabrication that reuses a genuine party token ("Board v. <fake>") or a one-letter
  caption; for those the resolved name is shown and the comparison is the lawyer's.
- Case-existence and the bundled opinion text cover a handful of pre-vetted cases,
  not the full reporter. A cite outside the corpus reads "not found", which is
  correct for the pre-vetted draft but is not a general coverage claim.
- Contract checking now evaluates every anchor type in a sentence, so a matching
  amount cannot mask a wrong date (a contradiction in any type wins). What remains
  unaligned is multiple values of the SAME type in one sentence against a clause
  that lists several (set-intersection, not role-aligned), which can still miss a
  contradiction. The pre-vetted summary is one value per sentence; do not invite
  multi-value-same-type edits on stage.
- Screenshots at 1440 and 1920 and the full `CLAUDE.md` verify chain (macOS build,
  swift test, evals, benchmarks) run on the demo machine, not in this worktree.
