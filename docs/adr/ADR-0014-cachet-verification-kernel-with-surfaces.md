# ADR-0014: Cachet is a Verification Kernel with Surfaces

- Status: Proposed
- Date: 2026-07-01
- References:
  - The companion repo (`~/Desktop/cachet-companion`): the second surface and
    the first re-vendored copy of the engine.
  - Honesty-parity corpus (`cachet-companion` commit `5f75ab8`): the shared
    verdict spec, step one of the kernel extraction.
  - This branch (`cachet/foundry-verify-hardening-2026-07-01`): the verify-surface
    and engine hardening this ADR generalizes from.
  - [ADR-0008](ADR-0008-v2-pivot-validation-first-sequencing.md) (V2 pivot: the
    independent verification layer), [ADR-0013](ADR-0013-semantic-subject-labeler.md).

## Context

Cachet exists as two products that share code: the Carrel/Codex app (the lectern
verify surface, examine, sealed briefs, vault) and the companion (a browser
extension plus a loopback bridge that verifies AI output ambiently). The
deterministic verify engine is implemented twice: `services/verify.py` +
`services/legal/*` in this repo, and a re-vendored `cachet_companion/verify/*`
in the companion.

The two copies are already drifting. In a single session the same
false-accusation class (footnote-strip over an enumerator, a quote present in an
un-retrieved passage) was fixed separately in both. That is the concrete cost of
treating them as two products: knowledge is duplicated, and it rots in place.

## Decision

Cachet is **one verification kernel with many surfaces**, structured in four
layers:

1. **Kernel (`cachet-verify`)**: the deterministic engine (quote, clause,
   citation, holding, three-state model). A deep module with a trivial
   interface, `verify(claim, source) -> verified | altered | could_not_check`,
   hiding all the hard logic. Pure, dependency-light, one source of truth.
2. **Trust spine**: the promises no cloud tool can structurally make, applied
   identically on every surface: on-device de-identification, zero-egress
   (loopback bridge, socket ban), the honest-refusal floor (refuse, never
   guess), provenance on every verdict, and sealed, SHA-256-certified, immutable
   briefs.
3. **Surfaces**: thin adapters that marshal input, call the kernel, render the
   verdict. The app (deliberate, document-in-hand) and the companion (ambient,
   in-browser) are the first two. An IDE/Docs sidebar, a CI/API gate, and a
   mobile companion are the same shape.
4. **Data plane**: vault (the user's documents), bounded public corpus, validity
   feed, sealed briefs (the audit trail), and the honesty-parity corpus (the
   spec every implementation answers to).

The load-bearing move is to **extract the kernel** so both surfaces import it and
the vendored fork is deleted. Sequence it as a strangler-fig, never a big-bang:
(1) a shared parity corpus as the verdict spec (done, `5f75ab8`); (2) the
companion adopts the packaged kernel; (3) the Carrel engine adopts it and the
`services/legal` duplication is removed. The honesty contract (three states,
never a false accusation, provenance on everything) is the forever-API that
every surface and every future embedder depends on; the parity corpus guards it.

A repo merge is explicitly rejected. It does not de-duplicate, and it would drag
the companion's zero-egress and dependency-light constraints into the heavy
monorepo. The problem is duplicated knowledge, not too many repos.

## Consequences

- A new surface becomes an adapter, not a rewrite. This is the whole leverage:
  the ceiling below is gated entirely on the kernel being extracted.
- The kernel is domain-agnostic. `verify(claim, source)` does not know it is
  legal; the same primitive generalizes to any domain with a source of truth.
  Legal is the wedge, not the boundary.
- At full extension, Cachet is a verification *layer*, not an app: an embedded,
  on-device kernel that stamps a provable "verified against source, on device,
  honestly" mark wherever an AI writes something a human will stake a decision
  on. The moat is the trust spine, which a cloud tool cannot replicate.
- Cost: the extraction is real work (packaging, two migrations). It is deferred
  behind validation and kill-dated; the parity gate is the interim guard against
  further drift.
- The one thing this ADR cannot decide: whether users value honest refusal
  enough to adopt it. That is the validation question, out of scope here. This
  ADR fixes the architecture; it does not claim the demand.
