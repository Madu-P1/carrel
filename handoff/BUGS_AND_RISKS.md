# Bugs And Risks

## Confirmed recently fixed

### Document/source identity in concept maps

Issue:
- Concepts and edges were not sufficiently document-aware.
- The graph could blur concepts from different uploaded files.

Fix:
- Added `concepts.doc_id`.
- Added `concept_edges.doc_id`.
- Backfilled those fields in DB migration.
- Updated ingestion, detail loading, graph fetching, and deletion to use explicit document ownership.

Primary code locations:
- `schema.sql:23`
- `schema.sql:33`
- `main.py:671`
- `main.py:750`
- `main.py:910`
- `main.py:982`
- `main.py:1657`

## Current known risks

### 1. Extraction quality is weak

Status:
- Not a crash bug, but a major product weakness.

Why:
- Concept extraction, summaries, questions, and cards are all heuristic.
- PDFs can produce poor text extraction and therefore poor concepts.

Likely fix:
- Introduce a proper extraction/normalization layer.
- Later replace concept/question generation with model-backed generation.

Current code locations:
- `main.py:456`
- `main.py:468`
- `main.py:517`
- `main.py:750`

### 2. Graph semantics are simplistic

Status:
- Functional, but weak.

Why:
- `ingest_document_record()` creates edges by zipping adjacent generated concepts.
- Relationships are inferred heuristically.
- Cross-document graphing within one subject is not semantically rich.

Likely fix:
- Store stronger source spans.
- Generate edges from chunk-level co-occurrence or model-assisted concept linking.

Current code location:
- `main.py:848`

### 3. Momentum engine is not fully source-aware

Status:
- Works, but is shallow.

Why:
- `build_momentum_engine()` still ranks concepts mostly by mastery/events/cards.
- It does not fully reason across subject grouping or document-level study trajectories.

Likely fix:
- Join concepts to documents earlier.
- Add subject-aware and time-series-aware ranking.

Current code location:
- `main.py:1248`

### 4. Large frontend state surface

Status:
- High fragility risk.

Why:
- `state` in `app.js` mixes all views and concerns.
- `loadBootstrap()`, `loadDocumentDetail()`, and `loadGraph()` have implicit ordering dependencies.

Risk pattern:
- A small render or selection change can break library/study/graph behavior together.

Current code locations:
- `app.js:263`
- `app.js:308`
- `app.js:380`
- `app.js:1086`
- `app.js:1207`

### 5. Large backend file

Status:
- Maintainability risk.

Why:
- `main.py` is a monolith.
- Persistence, migrations, heuristics, tutoring, and routes are coupled.

### 6. Missing browser tests

Status:
- Real gap.

Why:
- Backend unit tests pass, but no automated UI flow verifies DOM behavior.

### 7. SQLite migration strategy is minimal

Status:
- Acceptable locally, risky if schema evolves quickly.

Why:
- Startup migration logic uses ad hoc `ALTER TABLE` checks.
- There is no formal migration system.

Likely fix:
- Introduce Alembic or a simple versioned migration scheme.

## Fragile code areas to inspect carefully

### Backend

- `initialize_database()` for migration correctness
- `ingest_document_record()` for ownership and derived records
- `fetch_document_detail()` for document-scoped detail correctness
- `delete_document_record()` for orphan cleanup
- `fetch_graph()` for filter semantics
- `build_momentum_engine()` for stale assumptions

### Frontend

- `loadBootstrap()`
- `loadDocumentDetail()`
- `loadGraph()`
- `renderLibrary()`
- `renderConceptMap()`
- graph filter event listeners

## Concrete unfinished logic

### Source grounding

- Citations are chunk-backed, but not all tutor/compare logic is deeply grounded.
- There is no robust provenance UI beyond citation chips and previews.

### Subject grouping UX

- Users can assign a custom subject, but there is no dedicated subject-management screen.
- No merge/split/rename workflow for subject groups.

### Study queue UX

- SRS review works, but the study screen is still basic.
- No subject- or document-scoped queue controls.

### Notes/transforms

- Notes are persisted.
- Flashcard/quiz transforms are generated ad hoc and not saved as first-class artifacts.
