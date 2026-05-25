# Structural-citation gate (Gate 0) — 2026-05-22

## Problem

Carrel could produce an answer whose cited evidence is a **heading**, not
content. A heading node ("Chapter 3: Contract Formation") is a valid
verbatim substring of itself, so the existing quote check
(`validated_citation_quote`) passed it. The result is a grounded-looking
answer with no informational value: it echoes a section title back at the
user. Verbatim-correct, answer-empty.

## Root cause

Two gaps on the typed-node retrieval path:

1. `services/retrieval/node_type_router.py` listed `heading` in
   `_BASE_TYPES`, the default retrieval candidate pool. Its docstring
   called headings "prose". A heading carries a *label*, not an answer —
   that conflation is the bug. Any query with no trigger word ranked
   heading nodes against the query and could return one as a top hit.
2. Nothing downstream demoted a heading once retrieved. `HydratedNodeContext`
   did not even carry `node_type`, so the citation resolver could not
   have checked it.

`header` / `footer` were already excluded (router + ingest), so `heading`
was the only structural type leaking into citations.

## What shipped (Gate 0)

Deterministic elimination on the typed-node path. Headings are removed at
the source — they never reach the model as evidence — rather than caught
after the fact.

- **`NON_CITABLE_NODE_TYPES = {heading, header, footer}`** in
  `node_type_router.py` — single source of truth, imported by
  `services.tutor` and `evals.run_evals`.
- `_BASE_TYPES` is now `{body, list_item}`. The beacon value of headings
  is not lost: ingest copies each node's `heading_path` onto its
  body/list_item rows and `node_fts` indexes that column, so a query
  whose terms appear only in a section title still matches the
  answer-bearing nodes scoped under it.
- `HydratedNodeContext` gained a `node_type` field (default `"body"`).
- `_drop_non_citable_contexts` filters structural nodes out of citation
  context in `_hydrate_node_context` and on the scope-fallback path. A
  drop is logged (`tutor_structural_contexts_dropped`), never silent.
- The three `_fallback_contexts_from_scope_nodes` SELECTs now carry
  `n.node_type` so the fallback path is filtered too. This matters: the
  fallback orders by `reading_order`, and a document's first node is
  often its title.
- `evals/run_evals.py` reports `structural_citation_rate` (full mode);
  the harness warns if it is above 0. Regression gate.

Incidental fix: `log_event(LOGGER, "warning", ...)` in `_hydrate_from_nodes`
passed a string where `logging.Logger.log` requires an int level — a
latent crash on the orphaned-node path, masked only because its one test
mocks `log_event`. Corrected to `logging.WARNING` alongside the new call.

## Scope boundary

Gate 0 is the **typed-node path** (`RETRIEVAL_USE_NODES=true`). The legacy
chunks path is structurally untyped — a chunk window has no `node_type`,
so a heading line inside it cannot be caught by a type check. That needs
a heuristic and is Gate 1, not Gate 0; pretending a fuzzy heuristic is
"elimination" would be dishonest.

Gate 0 is also a precondition for flipping `RETRIEVAL_USE_NODES`
default-on (T12 Phase 4): the migration must not ship a known
valueless-answer hole.

## Deferred — answer-verification gates

- **Gate 1 — low-information body filter.** A `body` node that is itself
  not answer-bearing (a bare reference, a page number mis-typed as body,
  a fragment) and the chunks-path heading-line case. Deterministic
  heuristics (length, finite-verb presence), no model.
- **Gate 2 — semantic entailment verifier.** A surviving citation is real
  prose but does not actually support *this* claim. This is the only
  tier that needs a judge model. Candidate: Atla Selene-1-Mini (8B
  open-weights LLM-as-a-judge) run locally via Ollama as a new judge
  role, separate from the answering model. Land in the eval harness
  first (offline, no hot-path latency), as a parallel scorer, before any
  answer-time use.
