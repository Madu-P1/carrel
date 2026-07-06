# HELD design memo — wiring `cross_document` into the LIVE verdict path

STATUS: HELD, DESIGN ONLY. Nothing in this document ships, wires, or lands until
Madu signs. No `.py` file is touched by this memo. It supersedes the
`cross_document` sections of `docs/proposals/crossdoc-wiring.md` and
`docs/proposals/unified-wiring.md` for the LIVE path, because those were written
against a planned `engine_gateway.py` seam that the shipped detectors did not use
(see §1).

Written 2026-07-07, after the seven single-draft detectors landed live.

## 0. One-paragraph summary

The multi-document *input* surface already exists and is live: `/api/verify` plumbs
`doc_ids` + a SQLite `conn` end to end into `build_deterministic_envelope`. The
document text is reconstructable offline from the `nodes` table with a pattern the
envelope already uses. So `cross_document` is **reachable in the product today** — the
only real blockers are (a) a **finding-shape mismatch** (a cross-document finding is
inherently two-document; the live `structural_findings` channel is single-span) and
(b) two **scope decisions** (which documents to compare, and the `cross_document` vs
`crossdoc_ledger` overlap). This memo resolves both and gives a test-gated first slice.

## 1. Corrected baseline — what actually landed (read first)

`docs/proposals/unified-wiring.md` concluded there was "exactly ONE correct insertion
point," an uncommitted facade `services/engine_gateway.py` fanning every detector. That
is **stale for the live path.** The seven single-draft detectors were instead wired
**directly into `build_deterministic_envelope`** (`services/legal/deterministic_envelope.py`),
each as its own block before the envelope's `return`, emitting `StructuralFinding`
objects onto the existing `structural_findings` list. `engine_gateway.py` and
`verify_corpus` were never committed to `main`. Any `cross_document` wiring must target
the **same live seam the seven use**, not the gateway.

- Live seam: `build_deterministic_envelope(draft, *, conn, doc_ids, ...) -> dict`, key
  `structural_findings: list[dict]`.
- Live carrier: `services/verify.py::verify_draft` (line ~566) calls the envelope with
  `conn=conn, doc_ids=doc_ids`; the findings ride `VerifyResponse` generically.

## 2. The input surface is already live (grounded)

- `routes/verify.py:51` — `verify_service.verify_draft(conn, ..., doc_ids=payload.doc_ids)`.
  The request model already carries `doc_ids` (a list).
- `services/verify.py:566` — `build_deterministic_envelope(cleaned, conn=conn, doc_ids=doc_ids)`.
- `build_deterministic_envelope` signature already accepts `conn: sqlite3.Connection | None`
  and `doc_ids: Sequence[str] | None` (line ~975).
- Full document text is reconstructable **offline** from the DB with the pattern the
  envelope already uses in `_source_alias_table` (~line 647):
  `SELECT verbatim_text FROM nodes WHERE doc_id IN (...) ORDER BY doc_id, reading_order`.
  Grouping those rows **by `doc_id`** (instead of joining all together) yields exactly the
  `list[{doc_id, text}]` that `cross_document` consumes. No new I/O concept, no network.

Conclusion: no new input plumbing is required. This is the key finding — the "multi-doc
input surface" is not missing; it is already threaded to the seam.

## 3. The real blocker — finding shape

`detect_cross_document_contradictions(documents) -> list[CrossDocumentFinding]`
(`services/cross_document.py:486`) returns findings shaped:

```
CrossDocumentFinding(verdict, kind, term, dimension, detail, figures)
#   figures: tuple of per-figure dicts, each {document, surface, normalized,
#            hedge, start, end, snippet, copied}
```

A finding is **inherently ≥2 documents**: `figures[0]` lives in document A at its own
`start/end`, `figures[1]` in document B at its own `start/end`, and they disagree on
`term`/`dimension`. This does **not** fit `StructuralFindingItem` (single `span/start/end`
into one draft). `StructuralFinding.target` is a lone optional string — a cross-ref
target label, not a second document's located span. Forcing a two-document finding into
a single-span item would **lie about location** (which document, which offsets), and the
honesty floor forbids a finding that misstates where the conflict is.

### Recommendation: a SEPARATE `cross_document_findings` channel, not an overload

Add a new envelope key `cross_document_findings: list[dict]` with its own Pydantic item
model `CrossDocumentFindingItem` that carries `verdict` (→ disposition), `kind`, `term`,
`dimension`, `detail`, and `figures: list[FigureRef]` where each `FigureRef` is
`{document, start, end, snippet, surface, normalized}`. Rationale (Vulcan deep-module /
honest-shape):
- Keeps the single-span `StructuralFindingItem` contract intact (no ripple to the seven
  live detectors, the frontend `VerifyView`, or the `/api/verify` response_model for
  existing findings).
- Represents the two-document location **truthfully** — each figure names its own
  document + offsets.
- Zero-green invariant is preserved structurally: `CrossDocumentFinding.__post_init__`
  already rejects any verdict outside `{contradicted, could_not_verify}`; the item model
  mirrors that (`disposition` ∈ `{flagged, could_not_check}` only).

Rejected alternative — extend `StructuralFindingItem` with an optional `figures` list:
cheaper to wire but overloads a sealed single-span contract with a shape 99% of its
producers never use, and every consumer (frontend, tests) must now special-case it. The
wrong abstraction; a distinct channel is the deep module.

## 4. Scope decision A — which documents to compare

In the verify flow, `draft` is the text under audit and `doc_ids` are the **source**
documents it is checked against. Two readings:
- **(i) sources-only:** run `cross_document` over the `doc_ids` documents — "are the
  sources the draft cites mutually consistent?" Gated to `len(doc_ids) >= 2`.
- **(ii) draft-plus-sources:** add the draft as one more document in the set.

Recommendation: **ship (i) first.** It is the honest, well-defined question the detector
was built for (contradictions *among documents*), it needs no synthetic doc_id for the
draft, and the intra-draft contradictions are already covered by the seven live
detectors. (ii) is a clean follow-up once (i) proves out. Single-document verify runs
(the common case) are untouched: `< 2` documents → the pass is skipped, silent.

## 5. Scope decision B — `cross_document` vs `crossdoc_ledger` overlap

`crossdoc_ledger.detect_crossdoc_contradictions` widens the label side (colon /
section-qualified labels, case/whitespace normalization) and the figure side (calendar
dates, cross-currency refusals); it **overlaps** `cross_document` on quoted-defined-term
money/duration/percent/count conflicts (per `docs/proposals/crossdoc-wiring.md`).

Recommendation: **wire `cross_document` alone first** (narrower, the defined-term binding
comparison). Defer `crossdoc_ledger`. If both are wired later, dedupe on
`(term, dimension, frozenset(doc_ids in the finding))` at the seam so a conflict both
surface collapses to one — matching the existing proposal's dedup key. Do not wire both
in one slice; that reintroduces the double-report the campaign already flagged.

## 6. First test-gated slice (the concrete diff, when signed)

All additive; the seven live detectors and the single-span contract are untouched.

1. **Doc-text loader** in `deterministic_envelope.py`: a `_load_documents_by_id(conn,
   doc_ids) -> list[dict]` that runs the established `nodes.verbatim_text` query and
   **groups rows by `doc_id`** into `[{doc_id, text}, ...]`. Returns `[]` when
   `conn is None`, `doc_ids` has `< 2` entries, or the `nodes` table is absent (a
   chunks-path DB simply yields no cross-doc pass — silent, never an error).
2. **Corpus-level pass** in `build_deterministic_envelope`, before `return`: if the
   loader yields `>= 2` documents, call `detect_cross_document_contradictions`, map each
   `CrossDocumentFinding` → `CrossDocumentFindingItem`, and put them on a new
   `cross_document_findings` key. Wrap in the same guarded `try/except (ValueError,
   TypeError)` the other blocks use; bound the input (cap total document bytes, mirroring
   the `_TEMPORAL_MAX_CHARS` guard) so fact-ledger extraction over large corpora cannot
   hang the synchronous path.
3. **Contract + carrier:** add `CrossDocumentFindingItem` to `api_models.py` and a
   `cross_document_findings: list[CrossDocumentFindingItem] = []` field to
   `VerifyResponse`; thread the new envelope key through
   `services/verify.py::_verify_result_from_envelope`.
4. **Tests** (`tests/test_envelope_cross_document.py`): two source docs that contradict on
   a defined term → one flagged `cross_document` item whose two `figures` name the two
   `doc_id`s and offsets that index the real text; two consistent sources → nothing; a
   single document → nothing (pass skipped); every item validates against
   `CrossDocumentFindingItem`; the six-corpus honesty floor stays green at `--bar 0.0`;
   an oversized corpus completes fast (DoS guard). Then a **Mythos** pass before merge,
   per the campaign rule (five of seven wires had a real sealed-path bug the detector's
   own green tests missed).
5. **Frontend:** out of scope for the backend slice. Until `VerifyView` renders the new
   channel, the findings are API-visible only; flag that as the follow-up so the surface
   is not silently dark.

## 7. Open questions to confirm before building

- **`nodes` reading-order fidelity:** confirm `ORDER BY doc_id, reading_order` reconstructs
  each document's text faithfully enough for `cross_document`'s offset-bearing figures
  (the detector's `start/end` must index the reconstructed text, not the original upload).
  If nodes drop inter-node whitespace, the figure offsets are into the reconstruction —
  document that explicitly, as with the table_footing line→char note.
- **Which `doc_ids` reach a real verify call** in practice (does the product ever send
  `>= 2`?). If document-vault multi-select is not yet a live UX, the pass is correct but
  dormant; say so rather than imply coverage.
- **`crossdoc_ledger` decision** (§5) — defer, or wire both with dedup.
