# Learning OS API Contracts v2

These contracts are additive over the current API surface. Legacy routes can be preserved temporarily behind compatibility wrappers.

## Source ingestion

### `POST /api/sources/upload`

Request:

```json
{
  "file": "multipart",
  "source_name": "Cell Biology Week 2.pdf",
  "goal_id": "optional-goal-id",
  "source_kind": "uploaded_file",
  "metadata": {
    "subject_name": "Biology",
    "course_name": "BIO101"
  }
}
```

Response:

```json
{
  "source_id": "src_123",
  "status": "parsing",
  "source_version": 1,
  "duplicate_of": null
}
```

### `GET /api/sources`

Response fields:

- `id`
- `filename`
- `source_kind`
- `subject_name`
- `source_hash`
- `source_version`
- `parser_status`
- `duplicate_of`
- `artifact_stale_count`
- `health`

### `GET /api/sources/{source_id}`

Response fields:

- `source`
- `chunks`
- `diagnostics`
- `derived_counts`
- `stale_dependencies`

### `POST /api/sources/{source_id}/refresh`

Purpose:

- reparse and reindex the source
- detect changed chunks
- mark dependent artifacts stale

## Unified workspace

### `GET /api/workspace/v2`

Query params:

- `source_ids`
- `concept_ids`
- `goal_id`
- `surface`
- `session_id`

Response:

```json
{
  "scope": {},
  "next_action": {},
  "left_rail": {
    "sources": [],
    "goals": [],
    "notes": [],
    "sessions": [],
    "artifacts": []
  },
  "center_canvas": {
    "surface": "tutor",
    "payload": {}
  },
  "right_rail": {
    "evidence": [],
    "contradictions": [],
    "related_concepts": [],
    "next_actions": []
  }
}
```

## Tutor

### `POST /api/tutor/exchanges`

Request:

```json
{
  "session_id": "optional-session-id",
  "goal_id": "optional-goal-id",
  "source_scope": ["src_123"],
  "concept_scope": ["concept_123"],
  "mode": "tutor",
  "depth": "standard",
  "evidence_strictness": "citation-heavy",
  "question": "Explain mitosis vs meiosis",
  "selected_text": "optional excerpt",
  "learner_confidence": 62
}
```

Response:

```json
{
  "exchange_id": "tx_123",
  "answer": "string",
  "mode": "tutor",
  "classification": null,
  "evidence": [],
  "related_concepts": [],
  "next_actions": [],
  "confidence": 0.82
}
```

### `POST /api/tutor/exchanges/{exchange_id}/evaluate`

Request:

```json
{
  "learner_response": "The difference is that...",
  "mode": "examiner"
}
```

Response:

```json
{
  "classification": "wrong_relation",
  "repair_path": {
    "surface": "concept",
    "strategy": "causal_visual"
  },
  "revisit": {
    "schedule_in_minutes": 20
  },
  "evidence": []
}
```

## Concept graph

### `GET /api/concepts/graph/v2`

Query params:

- `source_ids`
- `concept_ids`
- `goal_id`
- `include_mastery=true`
- `include_misconceptions=true`

Node fields:

- `id`
- `title`
- `mastery_score`
- `source_count`
- `unresolved_question_count`
- `misconception_count`
- `related_cards`
- `evidence_refs`

### `GET /api/concepts/{concept_id}`

Response fields:

- `concept`
- `claims`
- `examples`
- `misconceptions`
- `related_concepts`
- `evidence`
- `artifacts`
- `review_summary`

## Notes

### `POST /api/notes`

Request:

```json
{
  "note_id": "optional",
  "note_type": "saved_insight",
  "goal_id": "optional-goal-id",
  "session_id": "optional-session-id",
  "source_id": "optional-source-id",
  "concept_id": "optional-concept-id",
  "title": "Chromosome checkpoint trap",
  "content": "string",
  "evidence_reference_ids": ["ev_1", "ev_2"]
}
```

### `POST /api/notes/{note_id}/transform`

Request fields:

- `target_kind`: `flashcard|quiz|outline|study_guide`
- `difficulty`
- `audience`

## Review

### `GET /api/review/queue`

Query params:

- `goal_id`
- `source_ids`
- `session_id`
- `include_missed=true`

### `POST /api/review/events`

Request:

```json
{
  "item_id": "card_123",
  "item_kind": "flashcard",
  "outcome": "missed",
  "classification": "misconception",
  "confidence": 28,
  "duration_seconds": 19
}
```

Response:

```json
{
  "next_due_at": "2026-04-13T10:00:00Z",
  "mastery_state": {},
  "next_action": {}
}
```

## Studio

### `POST /api/studio/artifacts`

Request:

```json
{
  "artifact_kind": "study_guide",
  "source_scope": ["src_123", "src_456"],
  "concept_scope": ["concept_1"],
  "goal_id": "goal_123",
  "audience": "self",
  "difficulty": "exam",
  "depth": "rigorous",
  "style": "concise",
  "output_length": "medium",
  "evidence_strictness": "citation-heavy",
  "custom_prompt": "Focus on causes and contrasts"
}
```

Response:

```json
{
  "artifact_id": "art_123",
  "status": "generating"
}
```

### `GET /api/studio/artifacts/{artifact_id}`

Response fields:

- `artifact`
- `versions`
- `prompt_text`
- `source_snapshot_hash`
- `evidence`
- `stale`
- `transforms`
- `exports`

### `POST /api/studio/artifacts/{artifact_id}/transform`

Request fields:

- `target_kind`
- `style`
- `difficulty`

## Cross-source synthesis

### `POST /api/synthesis/compare`

Request:

```json
{
  "source_scope": ["src_123", "src_456"],
  "concept_scope": ["concept_1", "concept_2"],
  "mode": "compare",
  "output_format": "report"
}
```

Response fields:

- `agreements`
- `contradictions`
- `gaps`
- `terminology_mismatches`
- `evidence`
- `artifact_id`

## Sessions

### `POST /api/sessions`

Request:

```json
{
  "goal_id": "goal_123",
  "source_scope": ["src_123"],
  "concept_scope": ["concept_1"],
  "mode": "focus_sprint",
  "difficulty_target": "standard",
  "duration_minutes": 20,
  "objective": "Understand checkpoints and cell-cycle control"
}
```

### `POST /api/sessions/{session_id}/complete`

Response fields:

- `mastery_delta`
- `weak_concepts`
- `generated_cards`
- `unresolved_items`
- `stretch_question`
- `revision_recommendation`
- `suggested_next_session`

## Export

### `POST /api/exports`

Request:

```json
{
  "object_kind": "artifact",
  "object_id": "art_123",
  "format": "markdown"
}
```

Response fields:

- `export_id`
- `status`
- `download_url`

## Staleness

### `GET /api/staleness`

Query params:

- `source_id`
- `status=stale`

### `POST /api/staleness/refresh`

Request fields:

- `source_id`
- `object_ids`
- `object_kind`
