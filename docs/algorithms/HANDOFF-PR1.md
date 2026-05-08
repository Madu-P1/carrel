# Handoff — implement PR 1 (typed nodes + Docling ingest)

> Paste this entire document as your first message to a fresh Claude Code session. It is self-contained.

---

## Mission

Implement PR 1 of the Ask pipeline rebuild. The full implementation plan is at [docs/algorithms/ask-pipeline-pr1-typed-nodes.md](./ask-pipeline-pr1-typed-nodes.md). Read it top to bottom before writing any code. The parent algorithm spec at [docs/algorithms/ask-pipeline.md](./ask-pipeline.md) gives the architectural why.

## Repo

`/Users/madu/Desktop/Codex` — work on a new branch off `main`. Suggested branch name: `pr1-typed-nodes`. Read [CLAUDE.md](../../CLAUDE.md) before touching anything; it documents the verify chain and the existing architecture.

## What "done" looks like

Every item on this checklist must be true:

1. **Migration `migrations/0016_nodes_typed.sql` lands** with the three tables (`nodes`, `node_embeddings`, `node_fts`) and the three FTS triggers, exactly as written in the plan doc. `uv run alembic` is not used here — the migrations are raw SQL run via the existing migration loader (look at how `0015` is invoked).
2. **`services/ingestion/typed_walker.py`** exists with the `TypedNode` dataclass and the `walk()` function. Verify the Docling element-iteration API against the actually-installed Docling version before committing the walker code; the `iterate_items()` call may need to be `iterate_elements()` or similar.
3. **`services/ingestion/docling_parser.py`** exists with `is_available()` and `parse_document()`. Graceful import fallback — if `docling` is not installed, `is_available()` returns `False` and the orchestrator skips the new path.
4. **`services/ingestion/persistence.py`** gains `insert_typed_nodes()`, `delete_typed_nodes()`, `embed_and_index_nodes()`. Follows the existing `chunks_vec` patterns in the same file.
5. **`services/ingestion/orchestrator.py::ingest_document_record`** has the new typed-node ingest hooked in **after** the existing chunks ingest, wrapped in a try/except so Docling failures never break the chunks path.
6. **Two env-var feature flags** plumbed: `INGEST_USE_DOCLING` (default false) and `INGEST_DOCLING_FORMATS` (default `pdf`).
7. **Five new test files** under `tests/`:
   - `test_typed_walker.py`
   - `test_typed_nodes_persistence.py`
   - `test_docling_pdf_ingest.py` (needs fixtures `tests/fixtures/single_column.pdf` and `tests/fixtures/two_column.pdf` — generate them with reportlab if they don't exist)
   - `test_docling_ingest_feature_flag.py`
   - Extend existing `test_db_migrations.py` with the `0016` round-trip
8. **`requirements.txt` updated** with `docling` pinned to a specific version. `requirements.lock` regenerated.
9. **`pytest tests/` passes** with the flag off. With `INGEST_USE_DOCLING=true` and `docling` installed, the new tests pass too.
10. **`./script/demo-readiness.sh` returns 8/8 green** (or whatever the current count is — match the existing baseline).
11. **The PR description in your final commit message** lists all four risks from the plan doc, with a one-line status for each.

## Hard rules

1. **Never change retrieval, UI, or any user-facing behavior in this PR.** The flag is off by default, the new path is parallel. Existing tests must pass without modification.
2. **Never let Docling break the chunks path.** Every Docling call sits inside try/except. Logged errors, never raised.
3. **Don't deprecate `chunks`, `chunks_fts`, `chunks_vec`.** They stay. PR 6 deletes them after parity is proven.
4. **Don't try to integrate Apple Vision OCR in this PR.** Ship with Docling's default `easyocr`. The Apple Vision swap is a follow-up.
5. **Don't try to align Docling char-offsets with the reader's pypdf-rendered text yet.** That's the open question flagged as Risk #4 in the plan. Document the gap in the PR description and leave it for PR 2.
6. **Don't add a new top-level dependency without justification.** `docling` is the only new top-level dep this PR adds. Anything else gets pushed back.

## Verification before you hand back

Run all of these in order. Paste the output (or summary) in your final report:

1. `git status` — clean tree, all changes committed.
2. `git log --oneline | head -10` — the new commits.
3. `pytest tests/ -x` with `INGEST_USE_DOCLING=false` (default) — must pass.
4. `INGEST_USE_DOCLING=true pytest tests/test_docling_pdf_ingest.py tests/test_typed_walker.py tests/test_typed_nodes_persistence.py tests/test_docling_ingest_feature_flag.py -x` — must pass.
5. `sqlite3 data/einstein_tutor.db ".schema nodes"` after running migrations — show the schema.
6. `./script/demo-readiness.sh` — report the count.

## When in doubt

If a decision isn't covered by the plan or this brief, ask Chimdindu before guessing. The cost of a 30-second clarification beats the cost of building the wrong thing for a day.

## Anti-patterns

These are real failures previous attempts have made on this codebase. Don't repeat them.

1. "I improved the chunker while I was in there" — no. Chunker is out of scope. Touch only what the plan touches.
2. "I added Pydantic models for the typed-node serialization" — no. The DB row IS the serialization. Don't add a parallel object model.
3. "I removed the old `chunks_vec` table because the new `node_embeddings` table replaces it" — no. Old tables stay until PR 6.
4. "I made the migration runner upgrade live data on startup" — no. New ingests get typed nodes; old documents stay on chunks until they're re-ingested manually.
