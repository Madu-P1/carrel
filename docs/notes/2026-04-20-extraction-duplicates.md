# Extraction Duplicate Audit

Date: 2026-04-20

## Result

The duplicate-source-of-truth issue has been resolved in three steps:

1. PR-C1 moved the canonical extraction stack behind the [`services/extraction/`](/Users/madu/Desktop/Codex/services/extraction) package, with [`services/extraction_pipeline.py`](/Users/madu/Desktop/Codex/services/extraction_pipeline.py) kept as the compatibility shim.
2. PR-C2 removed the legacy per-format parser layer from ingestion and routed shared role classification through [`services/extraction/quality.py`](/Users/madu/Desktop/Codex/services/extraction/quality.py).
3. PR-C3 replaced the old monolithic `services/ingestion.py` with the [`services/ingestion/`](/Users/madu/Desktop/Codex/services/ingestion) package, so the public `services.ingestion` import path now resolves to focused modules instead of a second extraction implementation.

## Live Caller Map

Canonical extraction callers:

- [`routes/documents.py`](/Users/madu/Desktop/Codex/routes/documents.py) calls `extraction_pipeline.extract_asset()` for uploads.
- [`routes/study.py`](/Users/madu/Desktop/Codex/routes/study.py) calls `extraction_pipeline.extract_asset()` for source-backed flashcard drafts.
- [`services/artifact_studio.py`](/Users/madu/Desktop/Codex/services/artifact_studio.py) calls `extraction_pipeline.extract_asset()` when regenerating grounded artifact context from file paths.
- [`services/ingestion/orchestrator.py`](/Users/madu/Desktop/Codex/services/ingestion/orchestrator.py) only accepts `IngestedAsset` as a typed ingestion input. It no longer owns any per-format parsing code.

Resolved duplicate sites:

- The legacy `_extract_*`, `_EXTRACTORS`, and `extract_text()` region was removed in PR-C2.
- Shared bullet / outline / footer / formula role logic now lives only in [`services/extraction/quality.py`](/Users/madu/Desktop/Codex/services/extraction/quality.py).
- `chunk_text()` remains as an ingestion-level manual-text helper in [`services/ingestion/concepts.py`](/Users/madu/Desktop/Codex/services/ingestion/concepts.py), while structured document chunking remains the responsibility of [`services/extraction/chunking.py`](/Users/madu/Desktop/Codex/services/extraction/chunking.py).

## Duplicate Pairs

### Per-format parsers

Present in both stacks:

- DOCX
- PPTX
- XLSX
- CSV / TSV
- HTML / XML
- JSON
- EPUB
- RTF

Decision:

- [`services/extraction/registry.py`](/Users/madu/Desktop/Codex/services/extraction/registry.py) is canonical for file parsing.
- The legacy ingestion-side parser duplicates are gone.

### Classification helpers

Present in both stacks:

- bullet detection / stripping
- outline detection
- footer / noise detection
- formula detection / role classification

Decision:

- [`services/extraction/quality.py`](/Users/madu/Desktop/Codex/services/extraction/quality.py) is canonical for shared span-role classification primitives.
- Ingestion topic mapping now imports those helpers instead of redefining them.

### Chunking

Present in both stacks:

- `services/ingestion.chunk_text()`
- `services/extraction.ChunkBuilder`

Decision:

- [`services/extraction/chunking.py`](/Users/madu/Desktop/Codex/services/extraction/chunking.py) `ChunkBuilder` is canonical for structured extracted elements.
- `chunk_text()` now exists only as a manual-text helper in the ingestion package.

## Final Layout

- Extraction:
  - [`services/extraction/__init__.py`](/Users/madu/Desktop/Codex/services/extraction/__init__.py)
  - [`services/extraction/registry.py`](/Users/madu/Desktop/Codex/services/extraction/registry.py)
  - [`services/extraction/parsers/`](/Users/madu/Desktop/Codex/services/extraction/parsers)
- Ingestion:
  - [`services/ingestion/__init__.py`](/Users/madu/Desktop/Codex/services/ingestion/__init__.py)
  - [`services/ingestion/orchestrator.py`](/Users/madu/Desktop/Codex/services/ingestion/orchestrator.py)
  - [`services/ingestion/text_utils.py`](/Users/madu/Desktop/Codex/services/ingestion/text_utils.py)
  - [`services/ingestion/concept_candidates.py`](/Users/madu/Desktop/Codex/services/ingestion/concept_candidates.py)
  - [`services/ingestion/concepts.py`](/Users/madu/Desktop/Codex/services/ingestion/concepts.py)
  - [`services/ingestion/answers.py`](/Users/madu/Desktop/Codex/services/ingestion/answers.py)
  - [`services/ingestion/topics.py`](/Users/madu/Desktop/Codex/services/ingestion/topics.py)
  - [`services/ingestion/cards.py`](/Users/madu/Desktop/Codex/services/ingestion/cards.py)
  - [`services/ingestion/questions.py`](/Users/madu/Desktop/Codex/services/ingestion/questions.py)
  - [`services/ingestion/relationships.py`](/Users/madu/Desktop/Codex/services/ingestion/relationships.py)

## Residual Follow-Up

- [`services/ingestion/concept_candidates.py`](/Users/madu/Desktop/Codex/services/ingestion/concept_candidates.py) and [`services/ingestion/orchestrator.py`](/Users/madu/Desktop/Codex/services/ingestion/orchestrator.py) are substantially smaller than the old monolith but still slightly above the ideal per-module target. The next cleanup pass should split phrase ranking from concept selection, and persistence steps from orchestration.
