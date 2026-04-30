import type { components, paths } from "./types.gen";

import { API_BASE, api } from "./client";

export type DocumentRow =
  paths["/api/documents"]["get"]["responses"][200]["content"]["application/json"][number];
export type DocumentUploadResponse =
  paths["/api/documents/upload"]["post"]["responses"][200]["content"]["application/json"];
export type DeleteDocumentResponse =
  paths["/api/documents/{doc_id}"]["delete"]["responses"][200]["content"]["application/json"];
export type DocumentDetail = components["schemas"]["DocumentDetailResponse"];
export type DocumentDetailDocument = components["schemas"]["DocumentListItem"];
export type UpdateDocumentSubjectRequest = components["schemas"]["DocumentSubjectRequest"];
export type TutorQueryRequest = components["schemas"]["TutorQueryRequest"];
export type TutorQueryResponse =
  paths["/api/tutor/query"]["post"]["responses"][200]["content"]["application/json"];

export const documents = {
  list: () => api<DocumentRow[]>("/api/documents"),
  upload: (file: File, subjectName: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("subject_name", subjectName);
    return api<DocumentUploadResponse>("/api/documents/upload", {
      method: "POST",
      body: form
    });
  },
  delete: (docId: string) =>
    api<DeleteDocumentResponse>(`/api/documents/${encodeURIComponent(docId)}`, {
      method: "DELETE"
    }),
  detail: (docId: string) => api<DocumentDetail>(`/api/documents/${encodeURIComponent(docId)}`),
  fileUrl: (docId: string) =>
    `${API_BASE}/api/documents/${encodeURIComponent(docId)}/file`,
  setSubject: (docId: string, subjectName: string) =>
    api<DocumentRow>(`/api/documents/${encodeURIComponent(docId)}/subject`, {
      method: "PUT",
      body: { subject_name: subjectName } satisfies UpdateDocumentSubjectRequest
    })
};

/**
 * Library-level operations (not tied to a single document). Separate object
 * because the backend groups them under /api/library/* for the same reason —
 * they act on the corpus as a whole.
 */
export interface DuplicateDocumentRow {
  id: string;
  filename: string;
  subject_name: string | null;
  file_type: string | null;
  upload_date: string | null;
  page_count: number | null;
  status: string | null;
  duplicate_of: string | null;
}

export interface DuplicateGroup {
  source_hash: string;
  canonical: DuplicateDocumentRow;
  duplicates: DuplicateDocumentRow[];
  total_cards: number;
}

export interface DuplicatePreview {
  groups: DuplicateGroup[];
  total_groups: number;
  total_duplicates: number;
  total_cards_in_duplicates: number;
}

export interface DuplicateCleanupResult {
  dry_run: boolean;
  groups: number;
  deleted?: number;
  would_delete?: number;
  cards_removed?: number;
  would_remove_cards?: number;
  plan: Array<{
    source_hash: string;
    kept: string;
    kept_filename: string;
    removed: string[];
    removed_filenames: string[];
    cards_removed: number;
  }>;
}

/**
 * Per-subject stats rendered by the Library home dashboard. First-failed-doc
 * lets the card render an inline error + Retry without a second round trip.
 */
export interface SubjectSummary {
  subject_name: string;
  source_count: number;
  failed_count: number;
  flashcard_count: number;
  last_studied_at: string | null;
  first_failed_doc: {
    id: string;
    filename: string;
    status: string;
    error: string;
  } | null;
}

export const library = {
  /** Preview every duplicate cluster. Read-only. */
  duplicates: () => api<DuplicatePreview>("/api/library/duplicates"),
  /** Execute the cleanup. Pass `{dryRun: true}` to compute the plan without
   *  mutating — useful for showing a final "about to delete N" confirmation. */
  cleanupDuplicates: (options: { dryRun?: boolean } = {}) =>
    api<DuplicateCleanupResult>(
      `/api/library/duplicates/cleanup${options.dryRun ? "?dry_run=true" : ""}`,
      { method: "POST" }
    ),
  /** Subject dashboard payload for the Library home grid. */
  subjects: () => api<{ subjects: SubjectSummary[] }>("/api/library/subjects")
};

/**
 * System-level signals for the sidebar footer.
 * Kept small on purpose — this is surface-adjacent metadata, not data the
 * app mutates. Extend only when adding a new visible indicator.
 */
export interface ProviderStatus {
  kind: "claude" | "ollama" | "null" | "unknown";
  ai_enabled: boolean;
  model_balanced: string;
  preference: string;
}

/**
 * Lightweight backend liveness check. The /api/health endpoint
 * touches no DB, no AI provider — just confirms the FastAPI process
 * is up and responding. The sidebar polls this every 10s to surface
 * a "backend offline" state to the user when the process dies (e.g.,
 * SIGTERM, OOM kill, BackendSupervisor's gap before it respawns).
 *
 * Returns the raw payload for callers that want to show the resolved
 * paths or document count; throws on any non-2xx or connection error.
 */
export interface BackendHealth {
  status: string;
  mode: string;
  documents: number;
  paths: { base_dir: string; db_path: string };
}

export const system = {
  provider: () => api<ProviderStatus>("/api/system/provider"),
  health: () => api<BackendHealth>("/api/health")
};

/**
 * Hybrid (FTS + vector) library search. Wraps `/api/search`, which fuses
 * BM25 keyword hits and dense-vector hits via reciprocal rank fusion in
 * `services.retrieval.search_hybrid`. Each result carries enough context
 * (filename, subject, page number) to render a result card without a
 * follow-up fetch per hit.
 *
 * `sources` reports which retriever surfaced the chunk: `["fts"]`,
 * `["vec"]`, or `["fts","vec"]`. Results that came from BOTH retrievers
 * are typically the strongest matches — the UI surfaces them with a
 * tighter accent.
 */
export interface SearchHit {
  chunk_id: string;
  doc_id: string;
  section: string | null;
  snippet: string;
  /** RRF-fused score; rank-relative, not a probability. */
  score: number;
  /** Which retrievers surfaced the chunk. */
  sources: ReadonlyArray<"fts" | "vec">;
  filename: string | null;
  subject_name: string | null;
  page_num: number | null;
}

export interface SearchResponse {
  query: string;
  results: SearchHit[];
}

export interface SearchParams {
  /** Required. Trimmed and length-capped server-side at 500 chars. */
  q: string;
  /** Optional cap on result count. Server enforces 1..50; default 12. */
  limit?: number;
  /** Optional subject filter, exact match. */
  subjectName?: string;
  /** Optional document filter; restricts hits to chunks of this doc. */
  docId?: string;
}

export const search = {
  query: (params: SearchParams) => {
    const qs = new URLSearchParams({ q: params.q });
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.subjectName) qs.set("subject_name", params.subjectName);
    if (params.docId) qs.set("doc_id", params.docId);
    return api<SearchResponse>(`/api/search?${qs.toString()}`);
  }
};

/**
 * Concept graph — nodes + edges across the user's library, scoped by
 * doc or subject. Positions (x, y) are pre-computed server-side via
 * `services.helpers.concept_positions`, so the renderer can place nodes
 * directly without running a client-side force-layout.
 *
 * Edge `relationship` is one of "supports" | "contrasts with" |
 * "includes" (the LLM extractor's vocabulary). Weight is 1 today;
 * future feedback signals may scale it.
 */
export interface ConceptGraphNode {
  id: string;
  document_id: string;
  raw_label: string;
  label: string;
  description: string | null;
  document_name: string | null;
  subject_name: string | null;
  mastery: number;
  x: number;
  y: number;
}

export interface ConceptGraphEdge {
  source: string;
  target: string;
  relationship: string;
  weight: number;
  document_id: string;
}

export interface ConceptGraphResponse {
  nodes: ConceptGraphNode[];
  edges: ConceptGraphEdge[];
}

export interface ConceptExplainResponse {
  concept: string;
  document_name: string | null;
  subject_name: string | null;
  level: number;
  explanation: string;
  takeaway: string;
  claims: Array<{
    id: string;
    claim_text: string;
    claim_type: string | null;
    confidence: number | null;
  }>;
  examples: Array<{
    id: string;
    example_text: string;
    example_type: string | null;
    confidence: number | null;
  }>;
  misconceptions: Array<{
    id: string;
    label: string;
    description: string | null;
    repair_strategy: string | null;
    confidence: number | null;
  }>;
}

export const concepts = {
  graph: (params: { subjectName?: string; docId?: string } = {}) => {
    const qs = new URLSearchParams();
    if (params.subjectName) qs.set("subject_name", params.subjectName);
    if (params.docId) qs.set("doc_id", params.docId);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<ConceptGraphResponse>(`/api/concepts/graph${suffix}`);
  },
  explain: (conceptId: string, level = 2) =>
    api<ConceptExplainResponse>(
      `/api/concepts/${encodeURIComponent(conceptId)}/explain?level=${level}`
    )
};

/**
 * Aggregated Dashboard payload. One read, one round trip — the Dashboard
 * view renders everything on first paint without secondary fetches.
 */
export interface DashboardActionTarget {
  label: string;
  path: string;
}

/** Compact active-session summary bundled into the dashboard payload so
 *  the status card renders on first paint without a second round trip. */
export interface ActiveSessionSummary {
  id: string;
  objective: string;
  mode: string;
  duration_minutes: number;
  started_at: string;
}

/**
 * One row of the Dashboard's "weak concepts" rail. Sourced from
 * `services.dashboard._weak_concepts`: concepts the user has actually
 * been tested on AND that score at or below the engine's fluency
 * ceiling (mastery <= 0.7). Closes the SRS-feedback loop by surfacing
 * what the mastery_engine has learned the user struggles with.
 *
 * `mastery` is a 0..1 float; the UI renders it as a small accent bar.
 * `last_tested` is a UTC ISO datetime string from the server.
 */
export interface WeakConcept {
  id: string;
  name: string;
  mastery: number;
  last_tested: string | null;
  document_id: string;
  document_name: string | null;
  subject_name: string | null;
}

export interface DashboardPayload {
  generated_at: string;
  greeting: {
    time_of_day: "morning" | "afternoon" | "evening" | "night";
    iso_date: string;
    display_date: string;
  };
  stats: {
    streak_days: number;
    streak_target_days: number;
    week_minutes: number;
    /** Exactly 7 floats, oldest to newest, minutes studied per day. */
    week_minutes_by_day: number[];
    sessions_today: number;
    due_cards: number;
    source_count: number;
    last_studied_at: string | null;
  };
  next_best_action: {
    kind: "import" | "review" | "session" | "explore";
    eyebrow: string;
    title: string;
    reason: string;
    primary: DashboardActionTarget;
    secondary: DashboardActionTarget | null;
  };
  active_session: ActiveSessionSummary | null;
  /** Up to 5 concepts the user has tested on AND is still failing
   *  (mastery <= 0.7). Empty list when nothing qualifies. */
  weak_concepts: WeakConcept[];
}

/** Full active-session response from the dedicated endpoint. Dashboard
 *  uses this for post-mutation refetch (after End Session) to avoid
 *  pulling the whole dashboard payload just to refresh one card. */
export interface ActiveSessionEnvelope {
  active_session:
    | (ActiveSessionSummary & {
        goal_id: string | null;
        difficulty_target: string;
        status: string;
      })
    | null;
}

/** Session completion payload — mastery delta, weak concepts, stretch
 *  question. Rendered as the "just-completed" state in the Active
 *  Session card. Not persisted: the user dismisses or navigates away
 *  and it's gone. Accepted trade-off per the autoplan gate. */
export interface SessionCompletionResult {
  session_id: string;
  mastery_delta: number;
  weak_concepts: string[];
  unresolved_items: string[];
  stretch_question: string;
  revision_recommendation: string;
  suggested_next_session: string;
  due_queue_count: number;
}

export const dashboard = {
  get: () => api<DashboardPayload>("/api/dashboard")
};

export interface StartSessionPayload {
  objective: string;
  mode: string;
  duration_minutes: number;
  /** Passed to backend as source_scope; we ship subject_name values and
   *  the backend does not treat them as doc IDs — the session engine
   *  stores them as free-form scope tags. Close enough for current use. */
  source_scope?: string[];
  concept_scope?: string[];
  goal_id?: string;
  difficulty_target?: number;
}

export interface StartedSession {
  id: string;
  objective: string;
  mode: string;
  duration_minutes: number;
  started_at: string;
  status: string;
}

export const sessions = {
  /** Lightweight: just the current active session (or null). */
  active: () => api<ActiveSessionEnvelope>("/api/sessions/active"),
  /** Start a session. Backend creates the row with status='active'. */
  start: (payload: StartSessionPayload) =>
    api<StartedSession>("/api/sessions", {
      method: "POST",
      body: {
        objective: payload.objective,
        mode: payload.mode,
        duration_minutes: payload.duration_minutes,
        source_scope: payload.source_scope ?? null,
        concept_scope: payload.concept_scope ?? null,
        goal_id: payload.goal_id ?? null,
        difficulty_target: payload.difficulty_target ?? null
      }
    }),
  /** Complete a session. Backend returns the mastery summary. */
  complete: (id: string) =>
    api<SessionCompletionResult>(
      `/api/sessions/${encodeURIComponent(id)}/complete`,
      { method: "POST" }
    )
};

/**
 * Notes — used by the Session view's Notes mode. Two endpoints:
 *   - save    → persists a note, optionally bound to the active session
 *   - expand  → AI-rewrites the note into structured markdown with
 *               summary, key ideas, organized notes, review prompts
 */
export interface SaveNotePayload {
  title: string;
  content: string;
  session_id?: string;
  doc_id?: string;
  concept_id?: string;
  note_type?: string;
}

export interface SavedNote {
  id: string;
  title: string;
  content: string;
}

export const notes = {
  save: (payload: SaveNotePayload) =>
    api<{ note: SavedNote }>("/api/notes", {
      method: "POST",
      body: {
        note_id: null,
        doc_id: payload.doc_id ?? null,
        concept_id: payload.concept_id ?? null,
        title: payload.title,
        content: payload.content,
        source_snippet: null,
        note_type: payload.note_type ?? "session_note",
        goal_id: null,
        session_id: payload.session_id ?? null,
        evidence_reference_ids: []
      }
    }),
  expand: (payload: { title: string; content: string }) =>
    api<{ expanded_markdown: string }>("/api/notes/expand", {
      method: "POST",
      body: payload
    })
};

export const tutor = {
  ask: (payload: TutorQueryRequest) =>
    api<TutorQueryResponse>("/api/tutor/query", {
      method: "POST",
      body: payload
    })
};

/** Backend shape from services/study.py::fetch_due_cards. Hand-typed since
 *  the endpoint is a loose Dict[str, object] on the Python side. Regenerate
 *  via `script/generate-api-types.sh` once the backend adds a Pydantic model
 *  for the response. */
export interface SrsDueCard {
  id: string;
  front: string;
  back: string;
  state: string;
  stability: number;
  difficulty: number;
  reps: number;
  lapses: number;
  due_date: string | null;
  concept: string;
  document_name: string;
  subject_name: string | null;
  raw_concept?: string;
}

export type SrsRating = "again" | "hard" | "good" | "easy";

export interface SrsReviewResponse {
  next_due_date: string;
  interval: number;
  ease: number;
}

/**
 * Shape returned by `GET /api/srs/cards` (services/study.py::list_cards).
 * Covers every column the Manage Cards view needs: source metadata, SRS
 * state, and the front/back so the user can read without flipping.
 */
export interface SrsCard {
  id: string;
  front: string;
  back: string;
  state: string;
  difficulty: number;
  reps: number;
  lapses: number;
  due_date: string | null;
  last_review: string | null;
  card_type: string | null;
  /** Null for user-authored "orphan" cards not tied to any concept. */
  concept_id: string | null;
  /** Null when concept_id is null, otherwise the cleaned concept label. */
  concept: string | null;
  raw_concept?: string | null;
  /** Null when the card has no concept / source document. */
  document_id: string | null;
  document_name: string | null;
  subject_name: string | null;
}

export interface CardCreatePayload {
  front: string;
  back: string;
  /** Optional. Omit to create an orphan card (shows up in "All subjects"). */
  conceptId?: string;
  /** Optional override. Defaults to "custom" on the server. */
  cardType?: string;
}

export interface CardAiDraftPayload {
  topic: string;
  context?: string;
  count?: number;
}

export interface CardAiDraftItem {
  front: string;
  back: string;
}

export interface CardAiDraftResponse {
  cards: CardAiDraftItem[];
  /** "ok" | "ai_disabled" | "ai_failed". The UI branches on this so a
   *  disabled provider renders a different empty state than an LLM that
   *  returned no usable drafts. */
  status: string;
  error?: string | null;
}

export interface SrsCardListResponse {
  cards: SrsCard[];
  total: number;
  limit: number;
  offset: number;
}

export interface SrsSubjectSummary {
  subject_name: string;
  card_count: number;
  due_count: number;
}

export interface SrsListParams {
  subject?: string;
  docId?: string;
  search?: string;
  limit?: number;
  offset?: number;
}

function srsListQuery(params: SrsListParams = {}): string {
  const search = new URLSearchParams();
  if (params.subject) search.set("subject", params.subject);
  if (params.docId) search.set("doc_id", params.docId);
  if (params.search) search.set("search", params.search);
  if (params.limit != null) search.set("limit", String(params.limit));
  if (params.offset != null) search.set("offset", String(params.offset));
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const study = {
  due: () => api<{ cards: SrsDueCard[] }>("/api/srs/due"),
  review: (cardId: string, rating: SrsRating) =>
    api<SrsReviewResponse>("/api/srs/review", {
      method: "POST",
      body: { card_id: cardId, rating }
    }),
  /** List every card in the library, filtered + paged. */
  listCards: (params: SrsListParams = {}) =>
    api<SrsCardListResponse>(`/api/srs/cards${srsListQuery(params)}`),
  /** Subjects with card + due counts — used by the filter chips. */
  subjects: () => api<{ subjects: SrsSubjectSummary[] }>("/api/srs/subjects"),
  /** Single delete. Returns `{deleted: 1}` on success, 404 if already gone. */
  deleteCard: (cardId: string) =>
    api<{ deleted: number }>(
      `/api/srs/cards/${encodeURIComponent(cardId)}`,
      { method: "DELETE" }
    ),
  /** Bulk delete. Returns actual rows removed, which may be less than ids.length. */
  bulkDeleteCards: (ids: string[]) =>
    api<{ deleted: number }>("/api/srs/cards/bulk-delete", {
      method: "POST",
      body: { ids }
    }),
  /**
   * Create a single card from the Manage Cards "New card" dialog. Orphan
   * cards (no concept) are allowed and surface under the "All" filter.
   */
  createCard: (payload: CardCreatePayload) =>
    api<{ card: SrsCard }>("/api/srs/cards", {
      method: "POST",
      body: {
        front: payload.front,
        back: payload.back,
        concept_id: payload.conceptId ?? null,
        card_type: payload.cardType ?? "custom"
      }
    }),
  /**
   * Ask the configured AI provider to generate flashcard drafts for a
   * topic. Returns drafts as {front, back} pairs; the user picks which
   * to save via the regular createCard endpoint, one per kept draft.
   */
  aiDraftCards: (payload: CardAiDraftPayload) =>
    api<CardAiDraftResponse>("/api/srs/cards/ai-draft", {
      method: "POST",
      body: {
        topic: payload.topic,
        context: payload.context ?? null,
        count: payload.count ?? 5
      }
    })
};
