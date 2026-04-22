# Eval Fixtures

These fixtures are intentionally small, text-only documents copied from the existing demo corpus so the smoke suite stays deterministic and cheap in CI.

- `cell_division.md` covers mitosis, meiosis, chromosomes, and checkpoints.
- `photosynthesis.md` covers chlorophyll, light-dependent reactions, the Calvin cycle, and stomata.

All fixture ingests use `subject_name="EvalBiology"` so eval cases can scope by subject without depending on runtime user data.
