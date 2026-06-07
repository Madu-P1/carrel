# T1 calibration corpus — labeling guideline (v1)

ADR-0012. This guideline governs the labeled, held-out legal corpus the T1 calibration
gate (`benchmarks/t1_calibration.py`) measures against. The corpus does not exist yet;
building it is the real critical-path dependency (PR-8), a data task, not a code task.
This file is hashed into the gate-pass artifact, so changing the guideline invalidates any
prior pass.

## The unit

One labeled example is a (premise clause, hypothesis sentence) pair:

- **premise**: a verbatim clause from a source document (an executed contract, or a cited
  opinion's holding statement).
- **hypothesis**: one sentence from an AI-drafted summary or brief that a reader might
  take to rest on that clause.

## The three labels

- **support** — the hypothesis is a faithful restatement of the premise. A careful reader
  would agree the clause says this.
- **contradict** — the hypothesis asserts something the premise rules out: an altered
  parameter (amount, term, party, date), a reversed obligation, a carve-out ignored.
- **cannot_determine** — the premise neither clearly supports nor clearly contradicts the
  hypothesis: the clause is silent on the point, the match is partial, or two careful
  readers could reasonably disagree.

## The hard rule: ambiguity defaults to cannot_determine

If two careful readers could disagree on support-vs-contradict, the label is
**cannot_determine**. The product's promise is no false affirmative; the gold must be
honest about the refusal state, never forced to a confident label to inflate coverage. A
label is `support` or `contradict` only when it is unambiguous.

## Splits

- Splits are **document-level disjoint**: every example from one source document lives in
  exactly one of train / dev / test (the gate enforces this as B8). A clause and its
  paraphrases never straddle the test boundary.
- **test** is double-blind labeled (two independent labelers, adjudicated by a third) and
  write-once: any edit bumps the corpus version and invalidates every prior gate-pass.
- Stratify by `surface` (litigator, contract) and by `gold_label` so each split carries
  enough affirmative examples to clear the gate's vacuous-pass floor.

## Worked examples

| premise (clause/holding) | hypothesis (draft sentence) | label |
|---|---|---|
| "The aggregate liability ... shall not exceed $500,000." | "Liability is capped at $500,000." | support |
| "The aggregate liability ... shall not exceed $500,000." | "Liability is capped at $1,000,000." | contradict |
| "The term continues for two (2) years." | "Either party may terminate for convenience on 30 days' notice." | cannot_determine |
