# Carrel Prompt Library

This directory versions the prompt catalog from `Prompt-Driven Improvement Plan for Carrel.pdf` as repo-local, deterministic templates. The prompts are advisory by default: they help produce audits, implementation plans, and reviews, but they do not call paid AI services or upload user documents unless explicit future configuration allows that.

## How To Use

Use `catalog.json` as the source of truth. Each prompt has stable metadata:

- `id`
- `category`
- `intent`
- `inputs`
- `outputs`
- `success_criteria`
- `risks`
- `model_notes`

Optional fields such as `template`, `sample_fixture`, and `expected_output_shape` let CI validate that prompts remain executable and that sample inputs cover every placeholder.

## Categories

- `ui_audit`: premium visual and component audits against `DESIGN.md`.
- `ux_flow`: task-flow analysis for import, reading, asking, reviewing, and onboarding.
- `frontend_perf`: render, scroll, bundle, and animation performance checks.
- `backend_api`: FastAPI route consistency, validation, and compatibility.
- `database`: SQLite migrations, indexes, WAL/backup checks, and sqlite-vec fallback.
- `accessibility`: keyboard, focus, names, roles, and contrast-sensitive checks.
- `metrics`: local-only, PII-free usage event taxonomy and instrumentation.
- `ci`: deterministic validation, smoke checks, advisory gates, and artifacts.
- `code_review`: risk-led code review prompts.
- `tests`: focused regression test planning.
- `usability_analysis`: end-to-end learner loop analysis.

## Validation

Run:

```bash
python3 script/validate_prompts.py
```

The validator checks required fields, category membership, unique IDs, placeholder coverage, fixture existence, and expected output-shape declarations. CI runs the same command in the Python quality job.
