# Foundry Universal-Engine Campaign — Retrospective (2026-07-06)

Campaign halted at the diminishing-returns point (fresh-run surface-memory reset
began re-treading built capabilities). Everything below is on branch
`cachet/foundry-final-2026-07-06` (commit `911ee273d`). **Nothing is wired into the
live verdict path** — every capability is a standalone, test-locked module with a
HELD wiring proposal awaiting Madu's signature.

## Totals
- ~7 armed runs, ~30 counted rounds, **~$280 total spend** (the big productive run
  alone = $128.62 for the 15 headline capabilities; earlier runs banked embeddability
  surfaces + the first detectors).
- **17 capability modules**, ~470 tests, ~230 labeled corpus cases.
- Honesty floor GREEN the entire campaign. Zero false-greens, zero false-accusations,
  parked surfaces never re-authored.

## The inventory

| # | Module | Tests | Corpus | Category | Verdict |
|---|---|---|---|---|---|
| 1 | `fact_ledger.py` | 25 | 16 | **Spine** — general two-surfaces-of-one-fact primitive | COMBINE (spine) |
| 2 | `fact_ledger_units.py` | 32 | 17 | **Spine** — dimensional/unit normalization layer | COMBINE (spine) |
| 3 | `fact_normal_form.py` | 27 | — | **Spine** — canonical fact form | COMBINE (spine) |
| 4 | `words_figures.py` | 20 | 20 | Intra-span detector | COMBINE (→ ledger extractor) |
| 5 | `enumeration_count.py` | 26 | 17 | Intra-span detector | COMBINE (→ ledger extractor) |
| 6 | `bound_pairs.py` | 28 | 17 | Intra-span detector | COMBINE (→ ledger extractor) |
| 7 | `date_duration_conflict.py` | 24 | 27 | Intra-span detector | COMBINE (→ ledger extractor) |
| 8 | `table_footing.py` | 41 | 21 | Domain — N-ary sum | KEEP |
| 9 | `code_claims.py` | 60 | 22 | Domain — Python AST | KEEP |
| 10 | `temporal_graph.py` | 35 | 17 | Domain — temporal obligations | KEEP |
| 11 | `crossref_integrity.py` | 48 | 20 | Domain — cross-ref / defined-term | KEEP (dedup: built twice) |
| 12 | `cross_document.py` | 28 | 18 | Ledger consumer — across ≥2 docs | KEEP |
| 13 | `crossdoc_ledger.py` | — | — | Round-2 re-tread of #12 | **DROP** |
| 14 | `engine_gateway.py` | 22 | — | Unification — one entry, fans to all | KEEP (VERIFY it's real, not a stub) |
| 15 | `verify_batch.py` | — | — | Embeddability — batch | KEEP |
| 16 | `stream_gate.py` | — | — | Embeddability — streaming | KEEP |
| 17 | `cachet_cli.py` | — | — | Embeddability — CLI | KEEP (dedup vs other CLIs) |
| + | `corpus_cache.py` | — | — | Efficiency — memoized corpus load | KEEP |
| + | runs 1-2: SARIF/JUnit/NDJSON adapters, pip console entry, library/batch APIs | — | — | Embeddability | DEDUP |

## The architecture (what the pile actually is)

Three layers emerged, whether or not the factory named them:

1. **The fact ledger is the spine.** `fact_ledger` + `fact_ledger_units` +
   `fact_normal_form` are one subsystem: a normalized, unit-aware ledger of "this fact
   asserted with this value here." The factory built them as three modules across three
   rounds; they are one thing.
2. **Detectors are two kinds.** The four *intra-span* detectors (words-figures,
   enumeration, bound-pairs, date-duration) were explicitly architected to feed the
   ledger — they extract a (fact, value, span) binding; the *ledger* does the
   contradiction logic. The four *domain* detectors (table-footing N-ary sums, code/AST,
   temporal graph, cross-ref) are genuinely distinct problems that do NOT reduce to
   two-surfaces-of-one-fact — they stay standalone.
3. **Cross-document + the gateway are consumers.** `cross_document` runs the ledger
   across ≥2 documents. `engine_gateway` is the one "everyone routes through this" entry
   fanning to every detector. These are the universality surface.

## COMBINE
- **Fold the spine into one subsystem** (`fact_ledger` + `_units` + `_normal_form` → one
  package with three files, one public entry). Three separate modules is an artifact of
  three separate rounds, not a design.
- ~~Recast the four intra-span detectors as ledger extractors.~~ **CORRECTED by the verify
  pass (2026-07-06): they do NOT collapse.** The four intra-span detectors detect a claim
  contradicting *itself within one span* (word-vs-figure, count-vs-list, floor>ceiling,
  date-vs-duration); the ledger detects *repeated-term* contradictions across a document.
  Different fact models — none of the four import the ledger's `Binding`/`extract_bindings`,
  and folding them in would lose their logic. Keep all four STANDALONE.
- **One CLI + one output layer.** Runs 1-2 produced overlapping entry points (CLI, batch,
  console-entry) and three output adapters (SARIF/JUnit/NDJSON). Front them all with the
  gateway + one CLI + one pluggable formatter.

## IMPROVE
- **VERIFY the gateway is real.** `grep` for detector imports in `engine_gateway.py`
  returned nothing — it may use dynamic dispatch/a registry, or it may be a thin stub that
  doesn't actually call the detectors. This is the single most important thing to confirm
  before trusting the "one entry fans to all" claim.
- **Wire the vetted subset into the engine.** Nothing routes to any of this yet. Per prior
  notes the real seam is `services/legal/deterministic_envelope.py`, **not**
  `services/verify.py`. `docs/proposals/unified-wiring.md` already consolidates the 18
  separate wiring docs — start there.
- **Re-run each module's own gate on the final tree** before wiring — several were built
  across runs with memory resets; confirm each still passes standalone.

## DROP
- **`crossdoc_ledger.py`** + its test — round-2 re-tread duplicate of `cross_document.py`.
- **The duplicate crossref build** — `crossref_integrity` was authored twice (run 6 + the
  resumed run's round 1); keep the stronger one, delete the other.
- **Redundant embeddability entry points** from runs 1-2 that the gateway now supersedes.
- **The ~18 individual wiring docs** once `unified-wiring.md` is confirmed to cover them.

## Recommended next action
1. **Verify pass** (I can spawn this): confirm the gateway actually wires the detectors,
   find the true duplicates, re-run every module's gate on the final tree, and check which
   intra-span detectors genuinely collapse into the ledger. Returns a grounded, file-and-line
   combine/drop list.
2. **Then wire a thin vertical slice** — pick ONE high-value detector (e.g. table-footing or
   cross-document), wire it through `deterministic_envelope.py` behind the honesty gate,
   land it as one reviewed PR. Prove the path end-to-end before wiring the rest.
3. Everything else stays HELD until the slice proves the wiring pattern.
