# Gate 1 — chunks-path structural-citation heuristic

> Successor to Gate 0 (`docs/notes/2026-05-22-structural-citation-gate.md`,
> shipped via PR #68 / commit `5a05879f`). Gate 0 closed the structural-
> citation hole on the typed-node path by typing it out. Gate 1 closes the
> same hole on the legacy chunks path, which has no `node_type` column to
> filter on. Deterministic heuristics, no model. Gate 2 (semantic
> entailment via Selene Mini) sits behind both and is out of scope here.
>
> **Revised 2026-05-25** after proponent/adversary/synthesizer routine.
> See ADR `docs/decisions/0004-gate-1-chunks-path-structural-citation-heuristic.md`
> for the debate transcripts and the four revisions baked into this doc:
> (1) quote-granularity predicate, not chunk-granularity; (2) new T2.0
> eval instrumentation sub-PR before T2; (3) labeled-slice escalated as
> operator-followup rather than self-resolved; (4) explicit T12 timing
> argument.

## Problem

A grounded answer can still cite a heading on the legacy chunks path
(`RETRIEVAL_USE_NODES=false`, the default until Phase 4 / T12 ships).
The Gate 0 typed-node fix relies on `nodes.node_type` to demote
structural rows. The chunks table has no equivalent column: a `chunks`
row is a paragraph-grouped 1200-character window (`services/ingestion/
concepts.py::chunk_text`) that can include a section title on one of
its lines.

Today's chunks path:

1. `services/tutor.py::_hydrate_from_chunks` returns
   `HydratedNodeContext` rows that default `node_type` to `"body"` (it
   is the dataclass default; the chunks row does not carry the field).
2. `_drop_non_citable_contexts` then filters on `node_type in
   NON_CITABLE_NODE_TYPES` and finds nothing to drop. The heading-line
   slips through to the LLM as evidence and can come back as a
   verbatim-correct, answer-empty citation.

The bug lives at sub-chunk granularity: the model picks which line of
a chunk to cite, and the answer-empty failure mode fires only when the
quoted substring IS the structural line. A chunk-text filter that
inspects the whole 1200-char window cannot distinguish a chunk whose
content happens to include one heading line from a chunk whose content
is mostly heading. The original revision of this plan proposed exactly
that chunk-text filter; the adversarial debate (ADR 0004) found it
mismatched to the problem's granularity. This revision pivots to the
cited quote string at resolve time.

## Why ship Gate 1 instead of accelerating T12

T12 (Phase 4.3 — flip `INGEST_USE_DOCLING` and `RETRIEVAL_USE_NODES`
default-on, run `script/reingest_all.py` against the live DB) is the
permanent fix. The adversary in the Gate 1 debate proposed redirecting
slot-1 effort toward unblocking T12 instead of building Gate 1. The
math on the redirect:

- T12's acceptance line in `AUTONOMOUS_WORK_PLAN.md` budgets ~2 hours
  of overnight re-ingest on the current 4-document corpus. Real
  user corpora scale linearly: a 50-document library takes ~25 hours.
- Post-T12, `RETRIEVAL_USE_NODES` defaults true but the chunks path
  stays QUERYABLE until T15 drops `chunks`, `chunks_fts`, `chunks_vec`.
  Any per-user re-ingest that fails halfway leaves the user on the
  chunks path with the structural-citation bug intact.
- T15 (chunks-table drop migration) is gated on T13 (port 8 remaining
  chunks readers to nodes). T13 is `pending` with no PR yet. Realistic
  sequencing puts T15 weeks out, not days.
- Gate 1 is ~300 lines with a hard sunset at T15. Throwaway code with
  a known retirement date is acceptable when the user-visible bug
  persists across the retirement window.

Gate 1 ships in days, fills the gap from "now" to "T15 lands cleanly
across every user's library." That gap is non-empty regardless of how
fast T12 lands.

## Why the chunks path cannot reuse `node_type`

The Docling-derived `nodes` table carries Docling's structural type per
row. The chunks table predates Docling. Backfilling `chunks.node_type`
would require re-parsing every existing chunk with Docling (and at
that point the user should just flip `RETRIEVAL_USE_NODES`, which IS
T12). So: build a content-shape detector, do not retrofit a column.

## Architecture: quote-granularity, not chunk-granularity

The predicate operates on the **cited quote string** at resolve time,
not on chunk content at hydration time. Two consequences:

1. **The heading-INSIDE-chunk case is caught.** A 1200-char chunk that
   opens with a 60-char heading and continues with 1100 chars of body
   passes through hydration unchanged. If the model cites the body
   line, the quote string is prose and survives the predicate. If the
   model cites the heading line, the quote string IS the heading and
   the predicate drops the citation.
2. **The false-drop surface shrinks.** A chunk full of code or short
   bullets is no longer dropped wholesale. Only quotes that are
   themselves shaped like structure are dropped.

The plug-in site is a single new pass inside
`services/tutor.py::_resolve_grounded_answer`, between quote
validation (`validated_citation_quote` already in place) and the final
answer assembly. The function signature:

```python
# services/retrieval/quote_heuristics.py  (new module)
def is_structural_quote(quote: str) -> bool:
    """True if `quote` matches a heading, bare-reference, or
    other low-information shape. Pure function, no I/O."""
```

In `services/tutor.py::_resolve_grounded_answer`, after each
`Citation` is validated:

```python
if chunks_heuristic_enabled() and is_structural_quote(citation.quote):
    log_event(
        LOGGER, logging.WARNING,
        "tutor_structural_quote_dropped",
        quote_preview=citation.quote[:80],
        node_id=citation.node_id,
    )
    structurally_dropped.append(citation.claim_index)
    continue
validated_citations.append(citation)
```

Claims whose only citations all got dropped move to
`unsupported_spans`, matching the existing "no silent fallback"
treatment of unsupported claims. The answer text is NOT dropped; the
user sees the answer with an honest "this claim is not supported"
note.

The filter applies on BOTH retrieval paths (nodes and chunks). On the
nodes path it is a no-op for well-typed nodes (Gate 0 already drops
those at retrieval time) and a backstop for the `body`-but-fragment
case Gate 0 explicitly deferred to Gate 1.

### Feature flag

- Env: `RETRIEVAL_CHUNKS_HEURISTIC` (boolean, default `true` since
  T4 flipped 2026-05-25). Name kept from the original plan despite
  the predicate now applying to both paths, because the chunks path
  is what the flag defends; the name documents intent. Operators
  opt out with `RETRIEVAL_CHUNKS_HEURISTIC=false`.
- Implementation: a single function in `services/retrieval/
  quote_heuristics.py::chunks_heuristic_enabled()` reading `os.getenv`.

## Three structural signals (applied to the quote string)

A cited quote is "structural" when it matches at least one of three
shape predicates. Signal aggregation simplifies at quote granularity:
the quote is short enough that one strong signal is sufficient.

### Signal 1 — Heading shape

A heading is short, has no terminal punctuation that suggests a
sentence, and lacks a finite verb.

- `is_heading_shape(quote) =
   len(quote.strip()) <= HEADING_MAX_CHARS
   AND not quote.strip().endswith(('.', '!', '?'))
   AND not _has_finite_verb(quote)`
- `HEADING_MAX_CHARS = 80` (env override `CARREL_HEADING_MAX_CHARS`).

The terminal-punctuation check is the key addition versus the
original plan: a short factual sentence like `"Photosynthesis is a
chemical process."` ends in a period and survives, even though it is
short and (assuming `_has_finite_verb` works) verb-bearing too. A
short list-item answer like `"Photosynthesis."` ends in a period and
survives. The heading case `"Chapter 3: Contract Formation"` has no
terminal punctuation, no finite verb, is under 80 chars, and fires.

### Signal 2 — Bare-reference shape

A reference fragment ("Smith 2019", "Fig. 4, p. 22", "[12]", or a
naked page number "237"):

- Numeric-only after stripping punctuation: `^[\d\.,;\-\s]+$`
- Author-year: `^[A-Z][a-zA-Z\-]+(\s+(et\s+al\.?|and\s+[A-Z][a-zA-Z\-]+))?,?\s+\d{4}[a-z]?$`
- Bracketed citation: `^\[\d+\]$` or `^\(\d+\)$`
- "See Figure X" / "p. N" / "Fig. N" patterns:
  `^(see\s+)?(fig(ure)?|table|chart|p)\.?\s+\d+`

Acceptance bar: the labeled eval slice (when it ships) shows >=30%
drop in structural-citation rate. Not "catch every reference shape."

### Signal 3 — All-caps or title-case banner

Many headings are styled. A quote where every word starts with a
capital letter and there is no finite verb is heading-shaped:

- `is_banner_shape(quote) =
   _all_words_titlecase(quote) AND not _has_finite_verb(quote)
   AND len(quote.split()) >= 2`

The two-word minimum avoids flagging proper nouns ("Einstein",
"Photosynthesis"). The verb gate avoids flagging title-case sentences
("Photosynthesis Captures Light" — a valid claim that should not
drop).

### Finite-verb detector (closed-class, no POS-tag dep)

A line "has a finite verb" if any whitespace-delimited token matches
the suffix set `{s, es, ed, ing, en}` with token base length > 2, OR
matches a small irregular-verb list (`is`, `are`, `was`, `were`,
`be`, `been`, `being`, `has`, `have`, `had`, `do`, `does`, `did`,
`can`, `could`, `will`, `would`, `shall`, `should`, `may`, `might`,
`must`).

At quote granularity, false positives (calling `things` a finite
verb) push the quote into "keep," which is the safe direction. False
negatives are the failure mode that matters; the quote-level scope
limits the blast radius to a single citation rather than a whole
context window.

**Kill condition for the verb detector:** if the labeled slice (T2 or
T3) shows a verb-detector false-drop rate > 5% — i.e. >5% of dropped
quotes are actually valid prose mis-classified as headings — pause
Gate 1 and open a separate ADR for whether to add spaCy
`en_core_web_sm` as a backend dep. Rationale for not deciding now: at
quote granularity the false-drop surface is smaller than the original
chunk-text design, and the empirical rate is the right gate for a
dep-weight decision.

## Where the predicate plugs in (concrete)

Single call site, replacing the original plan's three-site approach:

1. `services/tutor.py::_resolve_grounded_answer` — after the LLM
   citations are validated as verbatim substrings (existing flow),
   apply `is_structural_quote` to each citation's `.quote`. Drop
   structural citations, log the drop, move orphaned claims to
   `unsupported_spans`.

The function exits unchanged when `RETRIEVAL_CHUNKS_HEURISTIC=false`
(default until T4). The `_hydrate_node_context` /
`_drop_non_citable_contexts` chain at `services/tutor.py:615` stays
exactly as Gate 0 left it; this gate is additive at the resolve layer.

## Eval acceptance

**Pre-requisite (T2.0 below): the eval harness must measure chunks-
path `structural_citation_rate` before any acceptance gate fires.**

After T2.0 lands, two metrics, both measured against the canonical
full-mode eval suite (CLAUDE.md §Benchmarks+budgets):

1. **`structural_citation_rate`** on the chunks-path side of T08's
   comparison run (`RETRIEVAL_USE_NODES=false`) must drop by >=30%
   relative to the post-T2.0 baseline. The baseline is measured by
   T2.0 itself; the 30% is a measurable target, not an assertion.
2. **`groundedness@8`** must stay `>= 0.7` and must not regress more
   than 0.02 absolute against the post-T2.0 baseline. A larger drop
   means the heuristic is eating answer-bearing quotes and the
   predicate must loosen.

`quote_validity` is already 1.0 on the existing full-mode runs; the
heuristic does not touch the validator, so this stays where it is and
is reported as a sanity check.

## Sub-PR breakdown

### T2.0 — eval harness extension (new first sub-PR)

Lands changes to `evals/run_evals.py:470-490` so the chunks branch
(today `else: row = conn.execute("SELECT content FROM chunks ...")`
that only computes `quote_validity`) ALSO applies the shape detector
to `citation.quote` and increments `structural_citation_count` on a
structural match. The shape detector is a single import from the same
`services/retrieval/quote_heuristics.py` module the runtime filter
will use (one implementation, two call sites). The runtime filter
itself stays unimported / unused at this stage; T2.0 is measurement-
only.

Acceptance: full-mode eval suite runs with `RETRIEVAL_USE_NODES=false`
and reports a non-zero `structural_citation_count` (assuming the
corpus actually has structural-citation cases — Gate 0's investigation
showed it did). Comparison report at
`evals/reports/structural-citation-baseline-{date}.md` records the
measured baseline. This is the number against which T4's >=30%-drop
gate is measured.

### T2 — runtime quote-shape filter (heading + bare-reference signals)

Lands `services/retrieval/quote_heuristics.py` (new module) with
`is_structural_quote`, the three signal functions, and the
closed-class verb detector. Wires `_drop_structural_citations` into
`_resolve_grounded_answer`. Flag defaults `false`. Tests: unit tests
on `is_structural_quote` covering heading shape, bare-reference
shape, banner shape, and the false-drop cases (`"Photosynthesis."`,
`"E = mc²."`, `"def foo(): ..."`); integration test that asserts a
structural quote in a mocked LLM response gets dropped under the flag
and survives without it.

### T3 — tighten banner-shape signal + add bare-reference patterns

Tightens `is_banner_shape` based on T2's measurement (e.g. require
3+ words instead of 2 if banner false-drop is high). Adds 3-5 more
bare-reference regex patterns from the T2 measured baseline error
analysis. Same env flag. Same eval suite measures the second-round
drop.

### T4 — flip `RETRIEVAL_CHUNKS_HEURISTIC` default-on

Default change in `chunks_heuristic_enabled()`. Comparison report at
`evals/reports/compare-chunks-heuristic-{before,after}.md` runs full-
mode evals with the flag explicitly off then explicitly on. Acceptance
gate per the metrics section above: >=30% drop in
`structural_citation_rate` from the post-T2.0 baseline AND
`groundedness@8` within 0.02 of baseline.

## Labeled eval slice — escalated as operator-followup

The original plan included a new `evals/cases/structural-citation.jsonl`
labeled slice authored in slot 1. The adversary in ADR 0004 correctly
flagged this as slot-scope leakage (slot-1 TODOS says "stays out of
evals/ that isn't a smoke harness"). The labeled slice does not ship
in T2 or T3.

Instead, T2 ships an operator-followup entry asking:

> A labeled `evals/cases/structural-citation.jsonl` slice (20-30
> cases of grounded answers with known structural-citation traps)
> would let Gate 1 measure false-drop rate empirically. The slice is
> ~30s deterministic, smoke-shaped. Question for operator: does it
> ship in slot 1 (smoke-shaped exception applies), slot 2, or wait?

Gate 1 ships without the slice using the existing full-mode eval
suite. Slice-based false-drop measurement is a quality bonus, not a
prerequisite.

## Guards

- **No silent fallback.** Drops are logged via `log_event` like Gate 0,
  same field shape (`dropped`, `kept` -> `quote_preview`,
  `node_id`).
- **No regex catastrophic backtracking.** Patterns are simple linear
  matches against single quote strings under ~500 chars.
- **No spaCy / NLTK / POS-tagger dep.** Closed-class verb detector
  only. Kill condition: if false-drop rate > 5% on the eventual
  labeled slice, open a spaCy ADR.
- **No coupling to Docling.** This module never imports anything under
  `services/ingestion/`.
- **Gate 1 does not touch Gate 2.** Semantic entailment is a separate
  judge model with its own latency budget and its own deferred plan.

## Kill conditions

- T2 lands and the post-T2.0 baseline shows `structural_citation_rate`
  was already at zero on the chunks corpus. The bug class is empirically
  small; Gate 1 closes without T3/T4 and surfaces an operator-followup
  noting the unmeasured user-corpus risk remains.
- Any sub-PR's chunks-path `groundedness@8` regresses by more than 0.05
  absolute against the post-T2.0 baseline. Roll back, loosen
  thresholds, re-run before re-landing.
- After T4 ships the default-on flip, if real-user-anchored telemetry
  (when it exists) shows answer-empty rate UP rather than down,
  immediately flip `RETRIEVAL_CHUNKS_HEURISTIC=false` and reopen.

## Out of scope

- Replacing the heuristic with a tiny on-device classifier. Plausible
  next step after Gate 2 if structural noise persists, not in Gate 1.
- Re-parsing chunks with Docling. Equivalent to T12 and owned by
  slot 2 / the main routine.
- Cross-language heading detection (Carrel is en-US for now). The
  irregular-verb list is English-only and the bare-reference patterns
  assume Roman digits and Latin author names. Documented limitation.
- Adding spaCy. Deferred behind the false-drop kill condition above;
  if it fires, a separate ADR decides the dep-weight tradeoff with
  empirical evidence rather than assertion.

## Revisions log

- **2026-05-25 (this version):** rewrote after ADR 0004 debate verdict.
  Pivoted from chunk-text predicate to quote-string predicate. Added
  T2.0 instrumentation sub-PR. Removed labeled slice from T2 (now
  operator-followup). Added "Why ship Gate 1 instead of accelerating
  T12" section. Added terminal-punctuation gate to the heading shape
  signal (catches the false-drop on `"Photosynthesis."`). Added banner-
  shape signal (Signal 3). Reworked kill conditions and verb-detector
  escalation path.
- **2026-05-25 (initial draft):** chunk-text predicate design, three
  call sites in `services/tutor.py`, labeled slice in scope. Superseded
  by this revision and ADR 0004.
