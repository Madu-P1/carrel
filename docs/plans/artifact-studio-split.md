# Plan: Split `services/artifact_studio.py` (886 → <300 LoC)

**Branch:** `codex/fix-library-ingestion-subjects-reader`
**Audit reference:** path-from-65, "god-object services" item.

## Context

`services/artifact_studio.py` is the last remaining god-object on the audit's list. It mixes four cohesive concerns into one 886-LoC file:
1. Grounding/retrieval (chunk + concept loading for an artifact's scope)
2. Topic-map analysis (concept dominance, focus selection)
3. Artifact generators (9 generator functions: study guide, briefing, FAQ, flashcards, quiz, outline, summary, report, mock exam)
4. Orchestration + persistence (`generate_artifact`, `list_artifacts`, `get_artifact`)

Pattern is proven. We just shipped two equivalent splits:
- `services/tutor.py` 1133 → 936 (extracted notes/crud + tutor_quotes)
- `services/documents.py` 831 → 241 (extracted document_duplicates + library_subjects + concept_labels)

The most recent split was adversarially reviewed and returned **ship-able, zero findings**.

## Cohesive seams

| Seam | Lines | LoC | Concern | New module |
|------|-------|-----|---------|------------|
| A. Grounding | 44–275 | ~232 | Pull chunks + concepts + support snippets for an artifact scope | `services/artifact_grounding.py` |
| B. Topic map | 279–388 | ~110 | Dominant topic, importance scoring, focus selection, topic-map build | `services/artifact_topic_map.py` |
| C. Generators | 390–609 | ~220 | 9 `_generate_X()` functions + 3 item builders (flashcard, quiz, mock-exam) | `services/artifact_generators.py` |
| D. Orchestration (stays) | 611–886 | ~275 | `generate_artifact`, `list_artifacts`, `get_artifact`, `_hidden_artifact_payload` | `services/artifact_studio.py` (residual) |

After all three extractions, the residual file lands at ~275 LoC focused on orchestration + DB I/O — under the audit's <400 target.

## Public surface contract

External callers (greppable in the codebase):
- `routes/studio.py` imports `generate_artifact`, `list_artifacts`, `get_artifact`
- `services/jobs.py` may import `generate_artifact` for async generation
- Tests reference `services.artifact_studio.X` for mocking

All public names re-exported from `services/artifact_studio.py` (mirror tutor.py + documents.py pattern). Zero caller changes required.

## Execution order

1. **Seam A (grounding)** first — most self-contained, only `_concepts_for_scope` calls into `services.documents.collect_document_concepts` (clean dependency).
2. **Seam B (topic map)** — pure analysis, no DB I/O, easiest to test.
3. **Seam C (generators)** — biggest, but mechanical because each generator is independent.

Sequential, single-file writes (cannot parallelize — same residual file).

## Tests per seam

### `tests/test_artifact_grounding.py` (~10 tests)
- `_chunk_text_for_scope`: empty source_ids → returns all chunks; specific ids → filtered
- `_fresh_chunks_for_sources`: respects `chunks.embedding_status='ready'` filter
- `_concepts_for_scope`: doc_id missing → returns []; valid scope → enriches with display_name
- `_support_snippet`: pulls from highest-scored chunk; empty chunks → empty string
- `retrieve_grounding_chunks`: total budget capped per chunk
- `render_grounding_text`: chunk delimiters, content trimming

### `tests/test_artifact_topic_map.py` (~8 tests)
- `_clean_section_label`: drops boilerplate; empty → None
- `_clean_description`: HTML strip + whitespace collapse
- `_dominant_topic`: weighted by source_chunk count
- `_concept_importance`: mastery factor, description length
- `_select_focus_concepts`: caps at limit; ties broken alphabetically
- `_build_topic_map`: groups concepts by dominant topic; sorts by importance

### `tests/test_artifact_generators.py` (~12 tests)
- `_flashcard_items`: question/answer/source per concept
- `_quiz_items`: 4-option multiple choice, distractors per concept
- `_mock_exam_items`: pulls from topic map, balances across topics
- `_generate_study_guide`: depth=light vs deep produces different lengths
- `_generate_briefing`: includes top-N concepts
- `_generate_faq`: question-style headers
- `_generate_flashcard_set`: integrates deck_items if provided, else builds from concepts
- `_generate_outline`: hierarchical section structure
- `_generate_summary`: capped length
- `_generate_report`: includes goal context
- `_generate_mock_exam`: section per topic-map entry
- `_generate_quiz`: numbered questions

## Risk + mitigation

- **Low risk overall.** Pattern is proven 3x with adversarial-clean verdict.
- **Circular import risk:** Seam A's `_concepts_for_scope` calls `services.documents.collect_document_concepts`. Documents.py does NOT import artifact_studio, so no cycle. Direct module-level import is safe.
- **Test schema drift:** Like the documents.py split, tests use a minimal in-memory schema. Confirm queries don't need columns the test schema lacks.

## Verification gates

Per the standard run:
- `ruff check .` — must pass
- `mypy --config-file mypy.ini` — must pass
- `pytest tests/ --ignore=tests/test_eval_smoke.py -q` — must pass (currently 309)
- `tsc --noEmit` (frontend, sanity) — must pass
- Adversarial review (independent agent) — verdict must be `ship-able`

## NOT in scope

- LLM call refactors (the generators are template-heavy; no behavior changes here)
- New artifact types
- Performance tuning (`retrieve_grounding_chunks` budget logic stays as-is)
- Public API changes to `routes/studio.py`

## What already exists

- The split pattern: 3 prior extractions (`services/notes/crud.py`, `services/tutor_quotes.py`, the 3-module documents.py split)
- Re-export mechanism in `services/documents.py` lines 14-49 — copy this idiom
- Test schema fixtures (in-memory sqlite with column subsets) — see `tests/test_concept_labels.py::_connect()`

## Expected outcome

- `services/artifact_studio.py`: 886 → ~275 LoC (down 69%)
- Three new focused modules totaling ~560 LoC + their tests
- ~30 new unit tests
- 339+ backend tests passing (currently 309, adding ~30)
- Closes the audit's "god-object services" item completely
- Score lift: +1 toward 90 (per audit table)
