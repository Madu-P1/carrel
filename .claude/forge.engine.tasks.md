# Forge queue — Cachet deterministic verify engine

Drawn from the live TODOS.md engine backlog (2026-06-13). Each task is deterministic
(no model, no network), test-gated, additive, and independently shippable as one draft
PR. `pick: lowest-eligible` runs them in order; E1 is the lowest-risk (pure refactor)
and E2/E3 add new guards. Operator-gated and lawyer-validation-gated items (role-aligned
clause matching after T66, the T1 labeled corpus, clean-prose coverage wording) are
deliberately NOT queued here — they are not Forge-shippable without a human decision.

---

## E1 — Hoist per-node tokenization out of the deterministic verify hot path
- Status: todo
- Deps: none
- Source: TODOS.md "Perf (deterministic path at scale)"
- Why: `_clause_on_topic(sentence, clause)` (services/legal/deterministic_envelope.py:245)
  is called once per retrieved node (:533) and re-tokenizes + re-normalizes the SAME
  sentence on every call. The brief-level quote source pool is likewise rebuilt per quote
  instead of once per request. Both are pure CPU waste on the no-egress path; at brief
  scale (many sentences x many nodes) it dominates.
- Acceptance:
  - The sentence token set (and its trailing-s stopword fold) is computed ONCE per
    sentence and reused across all candidate clauses for that sentence — `_clause_on_topic`
    no longer re-tokenizes the sentence inside the per-node loop.
  - The brief-level quote source pool / alias table is materialized once per request, not
    once per quote.
  - Behavior is byte-identical: every assertion in `tests.test_deterministic_envelope`,
    `tests.test_contract_verify`, and `tests.test_quote_check` stays green unchanged.
  - Add a focused test that pins the new shape (e.g. the sentence-level token set is
    derived once and a multi-clause sentence produces the same on-topic decisions as a
    line-by-line baseline).
  - No new dependency, no network, no LLM. Zero-egress invariant holds.

## E2 — Corpus-completeness attestation: cross-check size/hash before honoring scope="complete"
- Status: todo
- Deps: none
- Source: TODOS.md "Corpus completeness attestation hardening" (flagged by adversarial review)
- Why: `CorpusManifest.scope` (services/legal/local_caselaw.py:49-88) currently lets an
  operator string alone decide that a citation miss reads the LOUD "no such case as of
  <as_of>". With `scope="complete"`, an operator-supplied manifest that does not actually
  match the loaded corpus turns every unbundled (but real) cite into a false "no such case".
  This is a false-accusation path — the most dangerous direction for the product.
- Acceptance:
  - `scope="complete"` is honored ONLY when the manifest's declared corpus size (and, when
    available, a content hash/fingerprint) matches the actually-loaded corpus. On any
    mismatch, a miss folds to the bounded-corpus could-not-check register, never the loud
    "no such case".
  - The demo manifest (`scope="demo"`) path is unchanged.
  - Tests pin BOTH directions: a matching complete manifest still earns the loud miss for a
    genuinely-absent cite; a mismatched/oversized complete manifest degrades a miss to
    could-not-check.
  - Zero-egress holds; no network introduced to compute the cross-check (it is over the
    locally-loaded corpus only).
- Note: touches `local_caselaw.py` / `case_verification.py` — the security human-gate will
  fire. That is correct; the operator reads the truth-surface change before it lands.

## E3 — Gate 1: deterministic low-information / heading filter on the legacy chunks path
- Status: todo
- Deps: none
- Source: TODOS.md Gate 1 row; docs/notes/2026-05-22-structural-citation-gate.md
- Why: Gate 0 closed the structural-citation hole on the TYPED-node path only. The legacy
  chunks path is structurally untyped, so a heading line (or a page-number/fragment
  mis-typed as body) inside a chunk window cannot be caught by a `node_type` check. It needs
  a deterministic heuristic (length floor, finite-verb presence, bare-reference detection)
  so a non-answer-bearing line can never become a citation on the chunks path.
- Acceptance:
  - A deterministic, model-free heuristic flags heading-shaped and low-information lines on
    the chunks path; import (do not re-derive) `NON_CITABLE_NODE_TYPES` from
    `services.retrieval.node_type_router` for the typed half and layer the heuristic only
    where type info is absent.
  - Answer-bearing prose is unaffected (no regression in citable-quote recall on the
    existing fixtures).
  - Tests cover: a bare heading is filtered; a page-number fragment is filtered; a real
    prose sentence survives; the heuristic is pure (same input -> same output, no I/O).
  - No model, no network. Zero-egress holds.
