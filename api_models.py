from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    card_id: str
    rating: str


class BulkDeleteCardsRequest(BaseModel):
    """Used by POST /api/srs/cards/bulk-delete. The frontend posts up to a
    few hundred ids at a time from the Manage Cards view. Keep it a plain
    list — SQLite can comfortably handle this size in one DELETE."""
    ids: List[str] = Field(default_factory=list)


class CardCreateRequest(BaseModel):
    """POST /api/srs/cards payload. The Manage Cards view posts this from
    the New Card dialog. concept_id is optional; orphan cards are allowed
    and surface in the "All" filter via LEFT JOIN. card_type defaults to
    "custom" so we can distinguish user-authored cards from those that
    the ingestion pipeline produced."""
    front: str = Field(..., min_length=1, max_length=4000)
    back: str = Field(..., min_length=1, max_length=4000)
    concept_id: Optional[str] = None
    card_type: str = Field(default="custom", max_length=64)


class CardAiDraftRequest(BaseModel):
    """POST /api/srs/cards/ai-draft payload. The "Generate with AI" mode of
    the New Card dialog sends a topic (required) and optional long-form
    context (pasted notes, a textbook excerpt). count is clamped server-side
    to 3-10 regardless of what the client sends."""
    topic: str = Field(..., min_length=1, max_length=400)
    context: Optional[str] = Field(default=None, max_length=8000)
    count: int = Field(default=5, ge=1, le=20)


class CardAiDraftItem(BaseModel):
    front: str
    back: str


class CardAiDraftResponse(BaseModel):
    cards: List[CardAiDraftItem]
    # status is one of: "ok" (AI produced drafts), "ai_disabled" (no
    # provider configured), "ai_failed" (provider returned ok=False or a
    # malformed payload). The client uses this to show the right empty
    # state instead of mis-diagnosing "zero drafts" as "AI returned nothing."
    status: str = "ok"
    error: Optional[str] = None


class QuizGenerateRequest(BaseModel):
    concepts: Optional[List[str]] = None
    count: int = 7
    difficulty: Optional[str] = None


class DialogueStartRequest(BaseModel):
    concept_id: Optional[str] = None


class DialogueMessageRequest(BaseModel):
    session_id: Optional[str] = None
    message: str
    concept_id: Optional[str] = None


class GoalRequest(BaseModel):
    goal: str


class StudyEventRequest(BaseModel):
    event_type: str
    doc_id: Optional[str] = None
    concept_id: Optional[str] = None
    confidence: Optional[float] = None
    duration_seconds: Optional[int] = None
    payload: Optional[Dict[str, Any]] = None


class TutorQueryRequest(BaseModel):
    question: str
    doc_id: Optional[str] = None
    concept_id: Optional[str] = None
    subject_name: Optional[str] = None
    selected_text: Optional[str] = None
    confidence: Optional[float] = None
    response_mode: str = "standard"


class TutorCitationItem(BaseModel):
    chunk_id: str
    document_id: str
    document_name: str
    section: Optional[str] = None
    page_num: Optional[int] = None
    snippet: str = ""
    content: str = ""
    score: float = 0.0
    label: str = ""


class TutorClaimItem(BaseModel):
    text: str
    citations: List[TutorCitationItem] = Field(default_factory=list)


class TutorActionItem(BaseModel):
    label: str
    mode: str


class TutorQueryResponse(BaseModel):
    answer: str = ""
    citations: List[TutorCitationItem] = Field(default_factory=list)
    source_cards: List[TutorCitationItem] = Field(default_factory=list)
    claims: List[TutorClaimItem] = Field(default_factory=list)
    unsupported_spans: List[str] = Field(default_factory=list)
    misconceptions: List[str] = Field(default_factory=list)
    scaffolds: List[str] = Field(default_factory=list)
    scaffold_steps: List[str] = Field(default_factory=list)
    actions: List[TutorActionItem] = Field(default_factory=list)
    selected_concept: Optional[str] = None
    grounded: bool = False
    model: str = ""
    latency_ms: float = 0.0
    cache_hit: bool = False
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    error: Optional[str] = None
    citation_attempt_count: int = 0
    citation_drop_count: int = 0
    citation_repair_count: int = 0
    momentum: Dict[str, Any] = Field(default_factory=dict)


class NoteUpsertRequest(BaseModel):
    note_id: Optional[str] = None
    doc_id: Optional[str] = None
    concept_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    source_snippet: Optional[str] = None
    note_type: str = "saved_insight"
    goal_id: Optional[str] = None
    session_id: Optional[str] = None
    evidence_reference_ids: Optional[List[str]] = None


class NoteTransformRequest(BaseModel):
    content: str
    doc_id: Optional[str] = None
    concept_id: Optional[str] = None


class NoteExpandRequest(BaseModel):
    content: str
    title: Optional[str] = None


class CompareRequest(BaseModel):
    left_id: str
    right_id: str


class DocumentSubjectRequest(BaseModel):
    subject_name: str


class DocumentListItem(BaseModel):
    id: str
    filename: str
    storage_name: Optional[str] = None
    subject_name: Optional[str] = None
    file_type: Optional[str] = None
    upload_date: Optional[str] = None
    page_count: Optional[int] = None
    status: Optional[str] = None
    source_kind: Optional[str] = None
    source_hash: Optional[str] = None
    parser_status: Optional[str] = None
    parser_diagnostics: Dict[str, Any] = {}
    confidence: Optional[float] = None
    duplicate_of: Optional[str] = None
    updated_at: Optional[str] = None
    extracted_at: Optional[str] = None
    summary: str = ""
    concept_count: int = 0
    question_count: int = 0


class DocumentChunkItem(BaseModel):
    id: str
    section: Optional[str] = None
    page_num: Optional[int] = None
    chunk_index: Optional[int] = None
    token_count: Optional[int] = None
    content: str = ""
    chunk_hash: Optional[str] = None
    provenance_json: Dict[str, Any] = Field(default_factory=dict)
    embedding_status: Optional[str] = None


class DocumentCounts(BaseModel):
    chunks: int = 0
    concepts: int = 0
    questions: int = 0
    cards: int = 0


class DocumentDetailResponse(BaseModel):
    document: DocumentListItem
    summary: str = ""
    concepts: List[Dict[str, Any]] = Field(default_factory=list)
    questions: List[Dict[str, Any]] = Field(default_factory=list)
    counts: DocumentCounts = Field(default_factory=DocumentCounts)
    concept_options: List[Dict[str, Any]] = Field(default_factory=list)
    chunks: List[DocumentChunkItem] = Field(default_factory=list)


class DocumentUploadResponse(BaseModel):
    doc_id: str
    filename: str
    file_type: Optional[str] = None
    page_count: Optional[int] = None
    storage_name: Optional[str] = None
    subject_name: Optional[str] = None
    status: Optional[str] = None
    source_kind: Optional[str] = None
    source_hash: Optional[str] = None
    parser_status: Optional[str] = None
    confidence: Optional[float] = None
    duplicate_of: Optional[str] = None


class DeleteResponse(BaseModel):
    deleted: bool


class DocumentSubjectUpdateResponse(BaseModel):
    document: DocumentListItem
    workspace: Dict[str, Any]


class TextDocumentCreateRequest(BaseModel):
    title: str
    content: str
    file_type: str = "txt"
    subject_name: Optional[str] = "General"


class TutorExchangeCreateRequest(BaseModel):
    question: str
    source_scope: Optional[List[str]] = None
    concept_scope: Optional[List[str]] = None
    goal_id: Optional[str] = None
    session_id: Optional[str] = None
    mode: str = "socratic"
    depth: str = "medium"
    learner_confidence: Optional[int] = None
    evidence_strictness: str = "grounded"


class TutorExchangeEvaluateRequest(BaseModel):
    learner_response: str
    mode: str = "quick_check"


class FlashcardDraftRequest(BaseModel):
    title: Optional[str] = None
    content: Optional[str] = None
    count: int = 8
    source_scope: Optional[List[str]] = None


class FlashcardDraftCard(BaseModel):
    q: str
    a: str
    type: str
    confidence: float
    topic: str
    supporting_chunk_ids: List[str]
    grounding_mode: str = "internal_only"
    show_citations: bool = False


class FlashcardDraftResponse(BaseModel):
    cards: List[FlashcardDraftCard]


class ReviewEventRequestV2(BaseModel):
    item_id: str
    item_kind: str
    outcome: str
    classification: str
    confidence: Optional[int] = None
    duration_seconds: Optional[int] = None
    goal_id: Optional[str] = None
    session_id: Optional[str] = None


class SessionStartRequest(BaseModel):
    objective: str
    goal_id: Optional[str] = None
    source_scope: Optional[List[str]] = None
    concept_scope: Optional[List[str]] = None
    difficulty_target: Optional[float] = None
    duration_minutes: int = 20
    mode: str = "mixed"


class StudioGenerateRequest(BaseModel):
    artifact_kind: str = "study_guide"
    source_scope: Optional[List[str]] = None
    concept_scope: Optional[List[str]] = None
    goal_id: Optional[str] = None
    session_id: Optional[str] = None
    audience: str = "student"
    difficulty: str = "standard"
    depth: str = "standard"
    style: str = "prose"
    output_length: str = "medium"
    evidence_strictness: str = "normal"
    custom_prompt: Optional[str] = None
    grounding_mode: str = "internal_only"
    show_citations: bool = False


class SynthesisRunRequest(BaseModel):
    source_ids: List[str]
    synthesis_type: str = "compare"
