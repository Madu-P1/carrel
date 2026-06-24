# Structural Integrity verification pillar

Spec date: 2026-06-24. Status: queued for Forge (engine contract `carrel-cachet-engine`).
Decision trail: pillar prioritization (Structural Integrity first) chosen 2026-06-24 over
the validate-first counter, after a product-planning brief + a touchstone ranking. The
counter (run a concierge test before building) is recorded and was overridden deliberately
for demo momentum; the held-out tests below are the ship authority regardless.

## What this is

A new verification surface that checks a single legal document for **internal**
consistency: references that point nowhere, defined terms that dangle, and values that
contradict themselves inside the same document. It needs no source corpus, no database, no
network, and no model. It is the purest expression of the deterministic moat and the
cheapest path to an undeniable "it caught X" demo moment.

## Why a new module, not a new disposition (design decision)

The existing engine (`build_deterministic_envelope`) is a **cross-document** verifier: it
checks a draft sentence against a source contract held in the `nodes` table, sentence by
sentence. It already grounds a draft's section/party references against the *source*
(`_source_party_section_sets`, `_grounding_reason`) as honest could-not-check, never an
accusation.

Structural integrity is a different mode: **intra-document**, whole-document, source-free.
"Does this document reference a Section 12 that it never defines" is answerable from the
document alone. Folding it into the per-sentence cross-document loop would couple two
analysis modes and muddy the existing verdict semantics. So it lives in a new pure module,
`services/legal/structural_integrity.py`, with its own finding type, and is surfaced into
the envelope **additively**. Truth surfaces stay clean and independently testable.

Counter considered: "reuse the existing loop / contract_verify." Rejected because the
existing loop requires a source and runs per sentence; structural integrity is documentwide
and source-free. The separation is the correct boundary, not duplication.

## Disposition model

New dataclass in `structural_integrity.py`:

```python
@dataclass(frozen=True)
class StructuralFinding:
    kind: str          # dangling_cross_reference | defined_term_unused | internal_contradiction
    disposition: str   # flagged | could_not_check
    detail: str        # human-readable, no green-badge language
    span: str          # the offending surface text, e.g. "Section 12.3"
    start: int
    end: int
    target: str | None = None  # normalized referent, e.g. "12.3"
```

Two dispositions only, mapped to the existing 3-state tray:
- `flagged` -> the refusal/catch register (the hero moment).
- `could_not_check` -> the honest could-not-check register.

There is deliberately **no `verified` card**. A reference that resolves is silent. This
holds the no-green-badge brand stance (the resolved case earns no reward; only the catch
and the honest gap surface). Honesty over coverage: every ambiguous case is
`could_not_check`, never a guess in either direction.

## The catch list (v1 scope), phased into Forge tasks

### SI-1 (hero): dangling intra-document cross-references

Detect a reference to a structural unit the document never declares.

- **References** come from the existing `_SECTION` detector (`anchors.py:138`): `Section`,
  `Sec.`, `Clause`, `Article`, `Schedule`, `Exhibit`, and the `§`/`§§` forms, with numbers
  like `12`, `4.2`, `7.2(a)`.
- **Declarations** (the targets) are detected by a new, conservative heuristic: a section
  token at the **start of a line** (after optional leading whitespace / numbering), which is
  how legal documents declare a heading. Reuse `_normalize_section` semantics for the match
  key so `Section 4.2`, `4.2`, and `§ 4.2` compare equal.
- **Rule:** a referenced `Section`/`Clause`/`Article` number with no matching declaration is
  a `dangling_cross_reference` -> `flagged`.

Zero-false-accuse guards (all mandatory):
- **Exhibit / Schedule references are never flagged.** They routinely point to externally
  attached material. A reference to `Exhibit A`/`Schedule 2` with no in-document
  declaration is `could_not_check` ("references an attachment not present in this
  document"), never `flagged`.
- **Fragment guard.** If the document has fewer than a small threshold of detected
  declarations (a pasted snippet, not a whole document), assert nothing: all references are
  `could_not_check`. We cannot claim a reference dangles when we may not hold the whole
  document.
- **Self-reference / range guard.** A reference inside its own declaration line, and a
  range form ("Sections 4 through 9"), are handled without false-flagging interior numbers.

This single task is independently shippable and is the demo hero on its own.

### SI-2: defined-term-defined-but-never-used

- Reuse `build_alias_table(text)` (`anchors.py:798`) to get the terms the document defines
  (`(the "Buyer")` and `"X" means ...`).
- Reuse `_defined_term_anchors` to count occurrences. A term whose only occurrence is at its
  definition site is `defined_term_unused` -> `flagged` (low severity, real and
  deterministic).
- **Used-but-never-defined is NOT flagged in v1.** Capitalized terms are everywhere (proper
  nouns, sentence starts, party names); flagging them would false-accuse. It is a documented
  recall gap; at most a `could_not_check` for a quoted term used in clear defined-term style
  with no matching definition, and only if it can be done without noise. Default: omit.

### SI-3: internal single-document contradiction (most guarded, lands last)

- Two anchors of the same type bound to the **same subject** with different canonical values,
  inside the same document, are surfaced as `internal_contradiction`. BUILT 2026-06-24 as
  `could_not_check`, NOT `flagged`: the adversary pass proved a bare proper-noun subject
  conflates "10% France tax" with "20% France tariff", so a confident flag would cry wolf.
  v1 is percent-only and honest ("possible inconsistency, review"); a loud flag awaits T1.
- **This task inherits the ADR-0013 constraint.** The AFM 3B subject-labeler failed and
  figures were scoped OUT of the confident/green path because subject-binding is unreliable.
  SI-3 must NOT reopen that: it fires only where subject-binding is already
  deterministic-safe (the conservative proper-noun-adjacency percent subject that D3 shipped,
  or an exact defined-term/party adjacency). Every unbound or weakly-bound pair is
  `could_not_check`. No new figure green path.
- Requires a `cachet-adversary` pass before it ships (engineered false-green and
  false-accuse attempts), with each surviving crack becoming a held-out test.

### SI-4: wire findings into the envelope + a source-free entry point

- Add a pure `check_structural_integrity(text: str) -> list[StructuralFinding]` that runs
  SI-1..SI-3 over a single document.
- `build_deterministic_envelope` gains an **additive** `structural_findings` key (list of
  serialized findings) computed over the draft. Existing `claims` / `unsupported_spans` /
  `provider` keys are untouched; every existing assertion stays green unchanged.
- Provide the source-free path so a lawyer can run integrity on one document with no source
  uploaded (the existing path requires `conn`/`doc_ids`).

### SI-5 (frontend, separate track, not in the engine contract)

Render `structural_findings` in the tray. Out of scope for the `carrel-cachet-engine`
Python contract; queued separately as an FE `[REVIEW]` task. Engine work lands first and is
testable headless without it.

## Demo script (the moment this buys)

A contract draft containing "...the indemnification obligations set forth in **Section 12.3**
shall survive termination..." where the document declares only Sections 1 through 9. The tray
flags: *"Section 12.3 referenced but not declared in this document."* No legal expertise
needed to see it is correct, and zero false-green risk: a missing declaration is a fact, not
a judgment.

## Invariants (every SI task)

- Pure functions: no network, no DB (SI-1..SI-3), zero-egress holds.
- Additive: existing engine assertions in `test_contract_verify`, `test_anchors`,
  `test_deterministic_envelope`, `test_quote_check` stay green **unchanged**.
- Honesty over coverage: ambiguity -> `could_not_check`, never a guess; no `verified` card.
- Independently shippable as one draft; REVIEW-gated (new truth-feeding module + an additive
  edit to `deterministic_envelope.py`).

## Held-out tests as ship authority (the real spec)

New `tests/test_structural_integrity.py`, matching the `verify_claim_against_clause` and
`BuildEnvelopeTests._build` styles. These cases are the acceptance bar; Forge ships only when
they pass and the existing suites stay green.

SI-1 (dangling cross-reference):
- A draft with "see Section 12" and declared sections 1-9 -> one `flagged`
  `dangling_cross_reference`, `target == "12"`.
- A draft with "pursuant to Section 4.2" where 4.2 IS declared -> no finding (silent).
- "as in Exhibit C" with no Exhibit C in the text -> `could_not_check`, never `flagged`.
- A two-line fragment with "see Section 8" and no declarations -> `could_not_check` (fragment
  guard), never `flagged`.
- "Sections 4 through 9" with 4..9 declared -> no false flag on interior numbers.

SI-2 (defined-term-unused):
- `"Confidential Information" means ...` defined, never used again -> `flagged`
  `defined_term_unused`.
- `(the "Buyer")` defined and used three times -> no finding.

SI-3 (internal contradiction):
- "10% to France ... later 20% to France" (same proper-noun subject) -> `flagged`
  `internal_contradiction`.
- "purchase price $1,000,000 ... a fee of $1,200,000" (different, unbound subjects) ->
  `could_not_check`, never `flagged` (no figure green path; ADR-0013).
- The cachet-adversary cracks, each pinned.

SI-4 (envelope wiring):
- `build_deterministic_envelope(draft_with_dangling_ref, ...)` returns a non-empty
  `structural_findings` list AND an unchanged `claims`/`provider` shape.
- `check_structural_integrity(text)` runs with no `conn`/`doc_ids`.

## Verify

The engine contract's `engine-suites` command, plus the new
`tests.test_structural_integrity`. Run before any SI task is considered done:

```
.venv/bin/python -m unittest tests.test_structural_integrity tests.test_contract_verify tests.test_contract_verify_integration tests.test_deterministic_envelope tests.test_anchors tests.test_quote_check -v
```
