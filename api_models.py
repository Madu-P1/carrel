from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


class ReviewRequest(BaseModel):
    card_id: str = Field(..., min_length=1, max_length=128)
    rating: Literal["again", "hard", "good", "easy"]


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
    the ingestion pipeline produced.

    PR 5.1 (ADR 0002) — `kind` is the render-mode discriminator. For
    `kind='qa'` (the default), front carries the question and back the
    answer. For `kind='cloze'`, both fields carry the same source
    sentence containing one `{{cN::term}}` marker — the client sends
    them mirrored so the schema invariant "both columns non-empty"
    holds without server-side mirroring. The service rejects cloze
    requests without a marker.
    """

    front: str = Field(..., min_length=1, max_length=4000)
    back: str = Field(..., min_length=1, max_length=4000)
    concept_id: Optional[str] = None
    doc_id: Optional[str] = None
    card_type: str = Field(default="custom", max_length=64)
    kind: Literal["qa", "cloze", "reverse"] = "qa"


class CardPairCreateRequest(BaseModel):
    """POST /api/srs/cards/pair payload. The "Reverse pair" mode of the
    New Card dialog sends a single front/back pair; the server inserts
    two srs_cards (the primary Q→A and the reverse A→Q) plus one
    card_pairs row in a single transaction. Both ids come back so the
    client can drop both rows into its cached list. concept_id +
    card_type behave the same as CardCreateRequest. PR 5.2 / ADR 0003.
    """

    front: str = Field(..., min_length=1, max_length=4000)
    back: str = Field(..., min_length=1, max_length=4000)
    concept_id: Optional[str] = None
    doc_id: Optional[str] = None
    card_type: str = Field(default="custom", max_length=64)


class CardPairCreateResponse(BaseModel):
    primary_id: str
    reverse_id: str


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
    count: int = Field(default=7, ge=1, le=25)
    difficulty: Optional[Literal["easy", "medium", "hard"]] = None


class DialogueStartRequest(BaseModel):
    concept_id: Optional[str] = Field(default=None, max_length=128)


class DialogueMessageRequest(BaseModel):
    session_id: Optional[str] = Field(default=None, max_length=128)
    message: str = Field(..., min_length=1, max_length=4000)
    concept_id: Optional[str] = Field(default=None, max_length=128)


class GoalRequest(BaseModel):
    goal: str = Field(..., min_length=1, max_length=1000)


class StudyEventRequest(BaseModel):
    event_type: str = Field(..., min_length=1, max_length=80)
    doc_id: Optional[str] = Field(default=None, max_length=128)
    concept_id: Optional[str] = Field(default=None, max_length=128)
    confidence: Optional[float] = Field(default=None, ge=0, le=100)
    duration_seconds: Optional[int] = Field(default=None, ge=0, le=86_400)
    payload: Optional[Dict[str, Any]] = None


class UsageEventRequest(BaseModel):
    event_name: str = Field(..., min_length=1, max_length=80)
    surface: Optional[str] = Field(default=None, max_length=64)
    properties: Dict[str, Any] = Field(default_factory=dict)


class UsageEventResponse(BaseModel):
    id: int
    event_name: str
    surface: Optional[str] = None
    properties: Dict[str, Any] = Field(default_factory=dict)
    created_at: str


class TutorQueryRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=4000)
    doc_id: Optional[str] = Field(default=None, max_length=128)
    concept_id: Optional[str] = Field(default=None, max_length=128)
    subject_name: Optional[str] = Field(default=None, max_length=160)
    selected_text: Optional[str] = Field(default=None, max_length=8000)
    confidence: Optional[float] = Field(default=None, ge=0, le=100)
    response_mode: Literal["standard", "concise", "exam", "socratic", "easier", "deeper"] = (
        "standard"
    )


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
    note_id: Optional[str] = Field(default=None, max_length=128)
    doc_id: Optional[str] = Field(default=None, max_length=128)
    concept_id: Optional[str] = Field(default=None, max_length=128)
    title: Optional[str] = Field(default=None, max_length=240)
    content: str = Field(..., min_length=1, max_length=40_000)
    source_snippet: Optional[str] = Field(default=None, max_length=8000)
    note_type: str = Field(default="saved_insight", max_length=64)
    goal_id: Optional[str] = Field(default=None, max_length=128)
    session_id: Optional[str] = Field(default=None, max_length=128)
    # Optional folder assignment for the global Notes page. When set,
    # the folder's subject wins over the document's subject in the UI.
    folder_id: Optional[str] = Field(default=None, max_length=128)
    evidence_reference_ids: Optional[List[str]] = None


class NoteFolderCreateRequest(BaseModel):
    """POST /api/notes/folders. The global Notes page posts this from
    inline "New folder" on each subject. subject_name is required so a
    folder always knows which subject group it belongs to; it defaults
    to the document's subject the user is filing from."""

    name: str = Field(..., min_length=1, max_length=120)
    subject_name: str = Field(..., min_length=1, max_length=160)


class NoteFolderUpdateRequest(BaseModel):
    """PATCH /api/notes/folders/{id}. Both fields are optional; the
    service patches only what's provided so rename and re-classify can
    travel independently."""

    name: Optional[str] = Field(default=None, min_length=1, max_length=120)
    subject_name: Optional[str] = Field(default=None, min_length=1, max_length=160)


class NoteMoveRequest(BaseModel):
    """PATCH /api/notes/{id}/folder. `folder_id=None` removes the note
    from any folder; it then falls back to its document's subject. A
    folder_id pointing at a non-existent row returns 400."""

    folder_id: Optional[str] = Field(default=None, max_length=128)


class NoteTransformRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=40_000)
    doc_id: Optional[str] = Field(default=None, max_length=128)
    concept_id: Optional[str] = Field(default=None, max_length=128)


class NoteExpandRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=40_000)
    title: Optional[str] = Field(default=None, max_length=240)


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
    parser_diagnostics: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
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


# ----------------------------------------------------------------------
# Calendar feeds + plan (Phase 1 of the coach feature)
# ----------------------------------------------------------------------


class CalendarFeedCreateRequest(BaseModel):
    """Body for POST /api/calendar/feeds.

    `color` is a hex string (#RRGGBB) the user picks at add time. Used
    by the WeekTimeGrid to color-code events from this feed; if absent,
    the frontend falls back to a deterministic per-feed default.
    """

    label: str = Field(..., min_length=1, max_length=120)
    url: str = Field(..., min_length=1, max_length=4096)
    color: Optional[str] = Field(default=None, max_length=32)


class CalendarFeedRow(BaseModel):
    """Response shape for feed rows. The `url` field is ALWAYS the
    masked form (`https://host/***`). Raw URL only echoes back on the
    initial POST response so the user can copy/verify.
    """

    id: str
    label: str
    url: str  # masked by route handler
    color: Optional[str] = None
    is_enabled: bool
    last_synced_at: Optional[str] = None
    last_successful_sync_at: Optional[str] = None
    consecutive_failures: int = Field(default=0, ge=0)
    last_error: Optional[str] = None


class CalendarFeedCreatedResponse(BaseModel):
    """Initial POST response. raw_url_echo is retained for compatibility
    but carries the masked display URL, never the secret raw feed URL.
    """

    feed: CalendarFeedRow
    raw_url_echo: str


class CalendarIcsUploadResponse(BaseModel):
    """Response for local .ics uploads.

    The uploaded file is parsed immediately and not retained on disk.
    `raw_url_echo` is a display label for compatibility with the feed
    dialog, never a local path or filename.
    """

    feed: CalendarFeedRow
    raw_url_echo: str
    items_seen: int
    items_upserted: int
    items_deleted: int


class LocalCalendarEventInput(BaseModel):
    """One EKEvent rendered for transport. Field bounds match what
    EventKit can return plus generous slack — a 4 KB title would be
    pathological but isn't impossible if a script writes one.
    """

    uid: str = Field(..., min_length=1, max_length=512)
    summary: str = Field("", max_length=4096)
    start_at: str = Field(..., min_length=1, max_length=64)
    end_at: str = Field(..., min_length=1, max_length=64)
    timezone: Optional[str] = Field(default=None, max_length=64)
    all_day: bool = False
    location: Optional[str] = Field(default=None, max_length=1024)
    status: Literal["confirmed", "cancelled", "tentative"] = "confirmed"


class LocalCalendarSyncRequest(BaseModel):
    """POST /api/calendar/local/sync body — one EKCalendar's worth of
    events. The macOS shell sends one of these per local calendar
    after EventKit grants access, and on every EKEventStoreChanged
    notification.
    """

    calendar_identifier: str = Field(..., min_length=1, max_length=256)
    label: str = Field(..., min_length=1, max_length=120)
    color: Optional[str] = Field(default=None, max_length=32)
    events: List[LocalCalendarEventInput] = Field(default_factory=list, max_length=10_000)


class LocalCalendarSyncResponse(BaseModel):
    feed_id: str
    items_seen: int
    items_upserted: int
    items_deleted: int


class CalendarEventRow(BaseModel):
    id: str
    feed_id: str
    summary: str
    start_at: str
    end_at: str
    timezone: Optional[str] = None
    all_day: bool
    location: Optional[str] = None
    status: Literal["confirmed", "cancelled", "tentative"] = "confirmed"


class StudySuggestionRow(BaseModel):
    id: str
    kind: Literal["study_block", "review_block", "catchup"]
    status: Literal["pending", "accepted", "dismissed", "expired"]
    start_at: str
    end_at: str
    due_at: Optional[str] = None
    reason_code: Literal[
        "free_block_overdue_srs",
        "deadline_imminent",
        "low_recent_review",
        "gap_between_classes",
    ]
    reason_text: str
    score: Optional[float] = Field(default=None, ge=0, le=1)


class PlanResponse(BaseModel):
    """GET /api/plan — the main read for the Plan view.

    `is_freshening` is the SWR signal: server has kicked off background
    refreshes for stale feeds, frontend renders a subtle "syncing"
    affordance until the next request returns it as false.
    """

    events: List[CalendarEventRow]
    suggestions: List[StudySuggestionRow]
    feeds: List[CalendarFeedRow]
    is_freshening: bool


class SyncFeedResponse(BaseModel):
    feed: CalendarFeedRow
    items_seen: int
    items_upserted: int
    items_deleted: int
    status: str
    error: Optional[str] = None


# ----------------------------------------------------------------------
# Public beta product-loop APIs
# ----------------------------------------------------------------------


class IngestionJob(BaseModel):
    id: str
    kind: str
    status: str
    stage: str
    filename: str
    subject_name: Optional[str] = None
    document_id: Optional[str] = None
    error: Optional[str] = None
    progress: float = Field(default=0, ge=0, le=1)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None


class JobEvent(BaseModel):
    id: int
    job_id: str
    event_type: str
    status: str
    stage: str
    message: Optional[str] = None
    payload: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None


class EvidenceResolution(BaseModel):
    document_id: str
    chunk_id: Optional[str] = None
    document_name: str
    section: Optional[str] = None
    page_num: Optional[int] = None
    quote_text: str = ""
    confidence: float = Field(default=0.5, ge=0, le=1)
    location_kind: Literal["page", "chunk", "bbox", "text_offset"] = "page"
    bbox: Optional[List[float]] = None
    text_offset_start: Optional[int] = None
    text_offset_end: Optional[int] = None


class AnchorCreateRequest(BaseModel):
    document_id: str = Field(..., min_length=1, max_length=128)
    quote_text: str = Field(..., min_length=1, max_length=8000)
    origin: Literal["highlight", "ai_answer_citation", "manual", "imported"] = "manual"
    promotion_state: Literal["weak", "saved", "carded", "mastered", "archived"] = "weak"
    chunk_id: Optional[str] = Field(default=None, max_length=128)
    page_num: Optional[int] = Field(default=None, ge=1)
    bbox: Optional[List[float]] = None
    text_offset_start: Optional[int] = None
    text_offset_end: Optional[int] = None
    user_question: Optional[str] = None
    claim_text: Optional[str] = None
    thread_id: Optional[str] = None
    confidence: Optional[float] = Field(default=None, ge=0, le=1)


class AnchorTransitionRequest(BaseModel):
    promotion_state: Literal["weak", "saved", "carded", "mastered", "archived"]
    srs_card_id: Optional[str] = Field(default=None, max_length=128)


class AnchorCardDraftRequest(BaseModel):
    count: int = Field(default=3, ge=1, le=3)


class AnchorPromotionRequest(BaseModel):
    front: str = Field(..., min_length=1, max_length=4000)
    back: str = Field(..., min_length=1, max_length=4000)
    card_type: str = Field(default="anchor", max_length=64)
    concept_id: Optional[str] = None


class DemoLibrarySeedResponse(BaseModel):
    seeded: bool
    documents: List[DocumentUploadResponse] = Field(default_factory=list)
    skipped_reason: Optional[str] = None
