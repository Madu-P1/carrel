# Einstein Tutor API Contracts

## Document Management

- `POST /api/documents/upload`
  - Request: multipart form with `file`
  - Response: `{ "doc_id": "string", "status": "processing" }`
- `GET /api/documents`
  - Response: document list
- `GET /api/documents/:id/status`
  - Response: `{ "doc_id": "string", "status": "processing|ready|error" }`
- `DELETE /api/documents/:id`
  - Response: `{ "deleted": true }`

## Quiz Engine

- `POST /api/quiz/generate`
  - Request: `{ "concepts": ["optional"], "count": 7, "difficulty": "easy|medium|hard" }`
  - Response: `{ "questions": [...] }`
- `POST /api/quiz/answer`
  - Request: `{ "question_id": "string", "response": "string", "time_taken": 12 }`
  - Response: `{ "correct": true, "feedback": "string", "mastery": 0.61 }`

## Concept Map

- `GET /api/concepts/graph`
  - Response: `{ "nodes": [...], "edges": [...] }`
- `GET /api/concepts/:id/explain?level=1`
  - Response: `{ "concept": "string", "level": 1, "explanation": "string", "takeaway": "string" }`

## SRS

- `GET /api/srs/due`
  - Response: `{ "cards": [...] }`
- `POST /api/srs/review`
  - Request: `{ "card_id": "string", "rating": "again|hard|good|easy" }`
  - Response: `{ "next_due_date": "2026-04-14", "interval": 3, "ease": 2.43 }`

## Socratic Dialogue

- `POST /api/dialogue/start`
  - Request: `{ "concept_id": "string" }`
  - Response: `{ "session_id": "string", "opening_prompt": "string" }`
- `POST /api/dialogue/message`
  - Request: `{ "session_id": "string", "message": "string" }`
  - Response: `{ "reply": "string", "understanding": 3 }`
