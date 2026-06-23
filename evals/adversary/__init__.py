"""Cachet adversarial discovery harness — the confession ledger.

A READ-ONLY red team against Cachet's deterministic verify engine. It generates
(claim, source) pairs whose honest verdict is provable by construction, runs each
through the REAL engine, and classifies every divergence as a crack. It edits no
engine file; it only calls the engine and reads the verdict back.

Entry point: ``python -m evals.adversary.harness``.

Constitution this harness exists to defend:
  - No false greens: the engine must never say ``supported`` on a claim that is
    not honestly supportable.
  - No false accusations: it must never say ``contradicted`` on a clean claim.
  - No laundering: a genuine contradiction must not be silently downgraded to
    could-not-check.

The harness mutates no engine truth-surface file. See
``docs/notes/2026-06-24-overnight-redteam-build.md`` for the build rationale and
``docs/decisions/0008-unattended-redteam-discovery-not-fix.md`` for the council
decision that scoped it to discovery-only.
"""
