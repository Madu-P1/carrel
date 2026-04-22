# Evals

This directory contains the local-first eval harness for grounded retrieval and tutor quality. The smoke suite is intentionally small and deterministic so it can run in CI without model credentials.

## Commands

- Run retrieval-only smoke metrics:
  - `python -m evals.run_evals --suite smoke --mode smoke`
- Run full grounded-tutor metrics:
  - `python -m evals.run_evals --suite smoke --mode full`

## Suite Shape

- `evals/fixtures/manifest.json` defines the demo corpus used by eval runs.
- `evals/cases/smoke.jsonl` defines cases against fixture filenames from the manifest.
- The runner ingests those fixtures into an isolated temporary database, resolves fixture filenames to actual `doc_id`s, and writes JSON plus markdown reports under `evals/reports/`.

## Current Gate Policy

- Smoke evals are blocking in CI for schema/loading and advisory for metric quality.
- Full evals are opt-in or scheduled because they call Claude and consume credits.
