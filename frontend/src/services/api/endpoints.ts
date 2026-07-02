import type { components, paths } from "./types.gen";

import { API_BASE, api } from "./client";
import { streamSse } from "./streaming";

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
export type VerifyRequest = components["schemas"]["VerifyRequest"];
export type VerifyResponse =
  paths["/api/verify"]["post"]["responses"][200]["content"]["application/json"];
export type VerifyClaimVerdict = NonNullable<VerifyResponse["claim_verdicts"]>[number];
/** One serialized case-verdict batch (the element shape of a claim's case_verdicts). */
export type VerifyCaseVerdictBatch = NonNullable<VerifyClaimVerdict["case_verdicts"]>[number];
/** One brief-level draft-quote-verbatim result (Cachet PR4). */
export type VerifyQuoteResult = NonNullable<VerifyResponse["quote_results"]>[number];
/** One render slice of an altered quote's autopsy tiling (Cachet quote autopsy). */
export type VerifyQuoteSegment = NonNullable<VerifyQuoteResult["segments"]>[number];
/** One document-level structural-integrity finding (Cachet SI-5). */
export type VerifyStructuralFinding = NonNullable<VerifyResponse["structural_findings"]>[number];

/** Cachet PR6 — Shelf persistence (saved briefs). */
export type BriefSaveRequest = components["schemas"]["BriefSaveRequest"];
export type BriefSummary = components["schemas"]["BriefSummary"];
export type BriefDetail = components["schemas"]["BriefDetail"];

/**
 * Events emitted by POST /api/verify/stream (Cachet PR3). This route returns a
 * StreamingResponse with no response_model, so it is absent from the generated
 * types.gen.ts; the event shape is hand-typed here (the documented pattern for
 * response_model-less routes). The backend
 * (`services.verify.verify_draft_stream`) streams the per-cite labor so the UI
 * shows it happening instead of waiting on a spinner:
 *   - `progress` once before the (atomic) extraction + LLM call
 *   - `claims` the skeleton cards (NO case verdicts yet, never a provisional pass)
 *   - `cite_verdict` per claim as its CourtListener + holding-match check lands
 *   - `result` the canonical payload, identical to POST /api/verify
 *   - `error` a surfaced failure (never swallowed); no `result` follows it
 * Safety invariant #6: a claim with no `cite_verdict` and no `result` must read
 * as could_not_check, never supported. The consumer enforces that.
 */
export type VerifyStreamEvent =
  | { type: "progress"; phase: string }
  | { type: "claims"; claim_verdicts: VerifyClaimVerdict[] }
  | { type: "cite_verdict"; claim_index: number; case_verdict: VerifyCaseVerdictBatch }
  | { type: "quote_batch"; quotes: VerifyQuoteResult[] }
  | { type: "result"; verify: VerifyResponse }
  | { type: "error"; error: string };

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

/** Vaults (document folders). A vault is a documents.subject_name; these endpoints
 *  let an empty vault persist (folder-first creation) and forget an empty one. */
export type VaultListResponse = components["schemas"]["VaultListResponse"];
export type VaultDeleteResponse = components["schemas"]["VaultDeleteResponse"];

export const vaults = {
  list: () => api<VaultListResponse>("/api/vaults"),
  create: (name: string) =>
    api<VaultListResponse>("/api/vaults", { method: "POST", body: { name } }),
  remove: (name: string) =>
    // Name travels as a query param (not a path segment) so a vault named after a
    // caption containing a slash can still be deleted; the path-param form 404s on
    // the encoded slash.
    api<VaultDeleteResponse>(`/api/vaults?name=${encodeURIComponent(name)}`, { method: "DELETE" })
};

export interface IngestionJob {
  id: string;
  kind: string;
  status: "queued" | "running" | "ready" | "partial" | "failed" | "cancelled";
  stage: "importing" | "extracting_text" | "ocr_fallback" | "indexing" | "generating_cards" | "ready";
  filename: string;
  subject_name: string | null;
  document_id: string | null;
  error: string | null;
  progress: number;
  created_at: string | null;
  updated_at: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface JobEvent {
  id: number;
  job_id: string;
  event_type: string;
  status: IngestionJob["status"];
  stage: IngestionJob["stage"];
  message: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
}

export const jobs = {
  import: (file: File, subjectName: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("subject_name", subjectName);
    return api<{ job: IngestionJob }>("/api/jobs/import", {
      method: "POST",
      body: form
    });
  },
  list: (limit = 50) => api<{ jobs: IngestionJob[] }>(`/api/jobs?limit=${limit}`),
  events: (afterId = 0) => api<{ events: JobEvent[]; last_event_id: number }>(`/api/jobs/events?after_id=${afterId}`),
  retry: (jobId: string) =>
    api<{ job: IngestionJob }>(`/api/jobs/${encodeURIComponent(jobId)}/retry`, {
      method: "POST"
    }),
  delete: (jobId: string) =>
    api<{ deleted: boolean }>(`/api/jobs/${encodeURIComponent(jobId)}`, {
      method: "DELETE"
    }),
  streamUrl: (afterId = 0) => `${API_BASE}/api/jobs/stream?after_id=${afterId}`
};

export interface EvidenceResolution {
  document_id: string;
  chunk_id: string | null;
  document_name: string;
  section: string | null;
  page_num: number | null;
  quote_text: string;
  confidence: number;
  location_kind: "bbox" | "text_offset" | "chunk" | "page";
  bbox: number[] | null;
  text_offset_start: number | null;
  text_offset_end: number | null;
}

export const evidence = {
  resolve: (params: { documentId: string; chunkId?: string | null }) => {
    const qs = new URLSearchParams({ document_id: params.documentId });
    if (params.chunkId) qs.set("chunk_id", params.chunkId);
    return api<EvidenceResolution>(`/api/evidence/resolve?${qs.toString()}`);
  }
};

export interface AnchorRecord {
  id: string;
  document_id: string;
  chunk_id: string | null;
  page_num: number | null;
  bbox: number[] | null;
  text_offset_start: number | null;
  text_offset_end: number | null;
  quote_text: string;
  user_question: string | null;
  claim_text: string | null;
  origin: "highlight" | "ai_answer_citation" | "manual" | "imported";
  promotion_state: "weak" | "saved" | "carded" | "mastered" | "archived";
  srs_card_id: string | null;
  thread_id: string | null;
  confidence: number | null;
  created_at: string;
  updated_at: string;
}

export interface AnchorCreatePayload {
  document_id: string;
  quote_text: string;
  origin: AnchorRecord["origin"];
  promotion_state?: AnchorRecord["promotion_state"];
  chunk_id?: string | null;
  page_num?: number | null;
  bbox?: number[] | null;
  text_offset_start?: number | null;
  text_offset_end?: number | null;
  user_question?: string | null;
  claim_text?: string | null;
  thread_id?: string | null;
  confidence?: number | null;
}

export interface AnchorCardDraft {
  front: string;
  back: string;
  duplicate_warning: boolean;
  source_anchor_id: string;
  supporting_chunk_ids: string[];
}

export const anchors = {
  create: (payload: AnchorCreatePayload) =>
    api<{ anchor: AnchorRecord }>("/api/anchors", {
      method: "POST",
      body: payload
    }),
  listForDocument: (documentId: string, pageNum?: number | null) => {
    const qs = new URLSearchParams();
    if (pageNum != null) qs.set("page_num", String(pageNum));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<{ anchors: AnchorRecord[] }>(`/api/anchors/document/${encodeURIComponent(documentId)}${suffix}`);
  },
  transition: (anchorId: string, promotionState: AnchorRecord["promotion_state"]) =>
    api<{ anchor: AnchorRecord }>(`/api/anchors/${encodeURIComponent(anchorId)}/transition`, {
      method: "POST",
      body: { promotion_state: promotionState }
    }),
  draftCards: (anchorId: string, count = 3) =>
    api<{ cards: AnchorCardDraft[] }>(`/api/anchors/${encodeURIComponent(anchorId)}/draft-cards`, {
      method: "POST",
      body: { count },
      timeoutMs: 120_000
    }),
  promoteCard: (anchorId: string, payload: { front: string; back: string; card_type?: string }) =>
    api<{ anchor: AnchorRecord; card: unknown }>(`/api/anchors/${encodeURIComponent(anchorId)}/promote-card`, {
      method: "POST",
      body: payload
    })
};

export const onboarding = {
  seedDemoLibrary: (force = false) =>
    api<{ seeded: boolean; documents: DocumentUploadResponse[]; skipped_reason: string | null }>(
      `/api/onboarding/demo-library${force ? "?force=true" : ""}`,
      { method: "POST" }
    )
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

export interface ShellStatus {
  due_count: number;
  doc_count: number;
  provider: ProviderStatus;
}

export const system = {
  provider: () => api<ProviderStatus>("/api/system/provider"),
  status: () => api<ShellStatus>("/api/shell/status"),
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
 * Free-tier Ask cards. Wraps `/api/ask/cards`, which runs the typed-node
 * hybrid retrieval (BM25 + vector + RRF, optional cross-encoder rerank)
 * and returns citation-ready cards. The cards ARE the answer — no
 * synthesis, no model hallucination surface. Each card carries
 * everything the UI + reader pane need to land the citation chip on
 * the exact passage: doc_id, page, char_start/char_end, verbatim_text,
 * heading_path.
 *
 * The endpoint exists in main behind no flag — the FRONTEND chooses
 * when to call it. Until char-offset alignment with the pypdf reader
 * is resolved (PR 4.2), card "Open" buttons navigate page-level only.
 */
export interface AskCard {
  /** rowid in the `nodes` table — the citation's complete identity. */
  node_id: number;
  doc_id: string;
  filename: string | null;
  subject_name: string | null;
  /** heading|body|list_item|caption|table_cell|equation|footnote|header|footer */
  node_type: string;
  /** "Chapter 3 > Photosynthesis > Light reactions" */
  heading_path: string;
  /** 1-indexed page number; null when the source has no pagination. */
  page: number | null;
  /** Char offsets into the document's canonical normalized text. */
  char_start: number;
  char_end: number;
  /** Exact substring — never normalized, never paraphrased. */
  verbatim_text: string;
  /** FTS5 snippet with <<>> highlight markers if the FTS retriever
   *  surfaced it; otherwise the verbatim_text trimmed to ~240 chars. */
  snippet: string;
  /** Final score: pure RRF (rerank off) or 0.7×rerank + 0.3×rrf (on). */
  score: number;
  /** Raw cross-encoder relevance in [0,1]; null when rerank off. */
  rerank_score: number | null;
  /** Which retriever(s) surfaced this card. Both = stronger match. */
  sources: ReadonlyArray<"fts" | "vec">;
}

export interface AskCardsResponse {
  query: string;
  cards: AskCard[];
  /** Library-wide totals so the UI can render an honest empty state
   *  ("ingest some documents first") vs "no hits for this query". */
  library: { total_nodes: number };
  rerank_used: boolean;
}

export interface AskCardsParams {
  /** Required. Trimmed and length-capped server-side at 500 chars. */
  q: string;
  /** Optional cap on result count. Server enforces 1..20; default 5. */
  limit?: number;
  /** Optional subject filter, exact match. */
  subjectName?: string;
  /** Optional document filter; restricts hits to one doc. */
  docId?: string;
  /** Override RETRIEVAL_USE_RERANKER env flag. Omit = follow flag. */
  useReranker?: boolean;
}

export const ask = {
  cards: (params: AskCardsParams) => {
    const qs = new URLSearchParams({ q: params.q });
    if (params.limit !== undefined) qs.set("limit", String(params.limit));
    if (params.subjectName) qs.set("subject_name", params.subjectName);
    if (params.docId) qs.set("doc_id", params.docId);
    if (params.useReranker !== undefined) qs.set("use_reranker", String(params.useReranker));
    return api<AskCardsResponse>(`/api/ask/cards?${qs.toString()}`);
  }
};

/**
 * Reader-side typed-node lookup (PR 4.2). Powers `?node=N` deep links
 * from Ask cards: the reader fetches THIS endpoint to learn the node's
 * page + verbatim_text, navigates to the page, and text-searches the
 * rendered DOM to highlight the exact passage.
 *
 * char_start / char_end are returned for future use — once a
 * canonical-text reader pane lands, the reader can scroll directly to
 * those offsets instead of doing a verbatim-text search.
 */
export interface ReaderNodeResponse {
  node_id: number;
  doc_id: string;
  filename: string | null;
  subject_name: string | null;
  /** heading|body|list_item|caption|table_cell|equation|footnote|header|footer */
  node_type: string;
  heading_path: string;
  /** 1-indexed page number; null when the source has no pagination. */
  page: number | null;
  char_start: number;
  char_end: number;
  verbatim_text: string;
}

export const reader = {
  fetchNode: (nodeId: number) =>
    api<ReaderNodeResponse>(`/api/reader/node/${encodeURIComponent(String(nodeId))}`)
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
  complete: async (id: string) => {
    const result = await api<SessionCompletionResult>(
      `/api/sessions/${encodeURIComponent(id)}/complete`,
      { method: "POST" }
    );
    // Notify shell-level signals (sidebar badge, today panel) that
    // SRS state just changed. Without this the sidebar's 30s poll
    // shows a stale "N due" badge while the user is already on the
    // "0 due" review queue page. The hook listens for the event and
    // re-fetches /api/shell/status.
    if (typeof window !== "undefined") {
      window.dispatchEvent(new CustomEvent("carrel:srs-changed"));
    }
    return result;
  }
};

/**
 * Notes — used by the Session view's Notes mode. Two endpoints:
 *   - save    → persists a note, optionally bound to the active session
 *   - expand  → AI-rewrites the note into structured markdown with
 *               summary, key ideas, organized notes, review prompts
 */
export interface SaveNotePayload {
  /** ID of an existing note to UPDATE. Omit for CREATE.
   *
   *  Critical: the server's upsert_note_record branches on note_id —
   *  truthy → UPDATE WHERE id=note_id, falsy → INSERT a new row. Until
   *  this field was added, every save call from the editor hardcoded
   *  null and silently created a duplicate note per autosave tick.
   *  See the fix commit for the screenshot of garbage rows that
   *  exposed it. */
  note_id?: string;
  title: string;
  content: string;
  session_id?: string;
  doc_id?: string;
  concept_id?: string;
  note_type?: string;
  /** Phase 2 — optional folder assignment for the global Notes page.
   *  When set, the folder's subject overrides the document's subject in
   *  the rail counts and the note tile. */
  folder_id?: string | null;
}

export interface SavedNote {
  id: string;
  title: string;
  content: string;
}

/** Full note row returned by `GET /api/notes` (services/tutor.py::fetch_notes).
 *  document_name / concept_name are JOINed in for display and are null when
 *  the note is not anchored to a document / concept.
 *
 *  `subject` is the resolved subject the global Notes page renders against:
 *  folder.subject_name > document.subject_name > "Unfiled". `folder_id` /
 *  `folder_name` are present when the note has been filed; both are null
 *  for unfoldered notes (reader notes default here). */
export interface NoteRecord {
  id: string;
  doc_id: string | null;
  concept_id: string | null;
  title: string;
  content: string;
  source_snippet: string | null;
  note_type: string;
  goal_id: string | null;
  session_id: string | null;
  folder_id: string | null;
  folder_name: string | null;
  subject: string;
  created_at: string;
  updated_at: string;
  document_name: string | null;
  concept_name: string | null;
}

export interface NoteFolderRecord {
  id: string;
  name: string;
  subject_name: string;
  sort_order: number;
  created_at: string;
  updated_at: string;
}

/** Response from `GET /api/notes/organization`. The global Notes page
 *  uses this for the left rail: it shows every subject that has at
 *  least one note, plus the folders that live under each subject. */
export interface NoteOrganizationSubject {
  name: string;
  note_count: number;
  folders: Array<{
    id: string;
    name: string;
    sort_order: number;
    note_count: number;
  }>;
}

export interface NotesListParams {
  doc_id?: string;
  concept_id?: string;
  /** Concrete folder id, or the literal string "none" to fetch only
   *  unfoldered notes. Mirrors the server's IS NULL handling. */
  folder_id?: string;
  subject_name?: string;
  limit?: number;
}

export const notes = {
  list: (params: NotesListParams = {}) => {
    const query = new URLSearchParams();
    if (params.doc_id) query.set("doc_id", params.doc_id);
    if (params.concept_id) query.set("concept_id", params.concept_id);
    if (params.folder_id) query.set("folder_id", params.folder_id);
    if (params.subject_name) query.set("subject_name", params.subject_name);
    if (params.limit != null) query.set("limit", String(params.limit));
    const suffix = query.toString();
    return api<{ notes: NoteRecord[] }>(`/api/notes${suffix ? `?${suffix}` : ""}`);
  },
  save: (payload: SaveNotePayload) =>
    api<{ note: SavedNote }>("/api/notes", {
      method: "POST",
      body: {
        note_id: payload.note_id ?? null,
        doc_id: payload.doc_id ?? null,
        concept_id: payload.concept_id ?? null,
        title: payload.title,
        content: payload.content,
        source_snippet: null,
        note_type: payload.note_type ?? "session_note",
        goal_id: null,
        session_id: payload.session_id ?? null,
        folder_id: payload.folder_id ?? null,
        evidence_reference_ids: []
      }
    }),
  expand: (payload: { title: string; content: string }) =>
    api<{ expanded_markdown: string; mode: "ai" | "deterministic"; error_code: string | null }>("/api/notes/expand", {
      method: "POST",
      body: payload,
      timeoutMs: 90_000
    }),
  organization: () =>
    api<{ subjects: NoteOrganizationSubject[] }>("/api/notes/organization"),
  folders: {
    list: (subject_name?: string) => {
      const query = new URLSearchParams();
      if (subject_name) query.set("subject_name", subject_name);
      const suffix = query.toString();
      return api<{ folders: NoteFolderRecord[] }>(
        `/api/notes/folders${suffix ? `?${suffix}` : ""}`
      );
    },
    create: (payload: { name: string; subject_name: string }) =>
      api<{ folder: NoteFolderRecord }>("/api/notes/folders", {
        method: "POST",
        body: payload
      }),
    update: (folderId: string, payload: { name?: string; subject_name?: string }) =>
      api<{ folder: NoteFolderRecord }>(`/api/notes/folders/${encodeURIComponent(folderId)}`, {
        method: "PATCH",
        body: payload
      }),
    remove: (folderId: string) =>
      api<{ deleted: boolean; folder_id: string }>(
        `/api/notes/folders/${encodeURIComponent(folderId)}`,
        { method: "DELETE" }
      )
  },
  /** Move a note into a folder, or pass `null` to unfile it. Lighter
   *  than `save` for the global page's "move to folder" dropdown — we
   *  don't have to round-trip the note's title/content just to refile. */
  move: (noteId: string, folderId: string | null) =>
    api<{ note: NoteRecord }>(`/api/notes/${encodeURIComponent(noteId)}/folder`, {
      method: "PATCH",
      body: { folder_id: folderId }
    }),
  /** Hard-delete a note. The backend cascades evidence rows; the row
   *  is gone for good. The editor and the tile context menu both
   *  call this with an explicit user confirmation upstream. */
  remove: (noteId: string) =>
    api<{ deleted: boolean; note_id: string }>(
      `/api/notes/${encodeURIComponent(noteId)}`,
      { method: "DELETE" }
    )
};

export const tutor = {
  ask: (payload: TutorQueryRequest) =>
    api<TutorQueryResponse>("/api/tutor/query", {
      method: "POST",
      body: payload,
      timeoutMs: 180_000
    })
};

// Carrel V2 Stage 1 — Verify-mode endpoint.
export const verify = {
  draft: (payload: VerifyRequest) =>
    api<VerifyResponse>("/api/verify", {
      method: "POST",
      body: payload,
      timeoutMs: 180_000
    }),
  /**
   * Stream verification verdicts (Cachet PR3). Yields each VerifyStreamEvent as
   * it arrives so the caller can ink in the per-cite labor. The final `result`
   * event carries the same payload as `verify.draft`. Pass an AbortSignal to
   * cancel an in-flight verification.
   */
  draftStream: (payload: VerifyRequest, opts?: { signal?: AbortSignal }) =>
    streamSse<VerifyStreamEvent>("/api/verify/stream", payload, opts)
};

/**
 * Cachet PR6 — the Shelf. Saved briefs: a checked draft plus its full verify
 * response and the client-built certification, kept so the lawyer can return
 * to one and re-hydrate the Verify view without a re-verify.
 */
export const briefs = {
  /** Save a checked draft. Returns the lean summary (no draft/response/cert). */
  save: (payload: BriefSaveRequest) =>
    api<{ brief: BriefSummary }>("/api/briefs", {
      method: "POST",
      body: payload
    }),
  /** All saved briefs, most-recent-first. Summaries only. */
  list: () => api<{ briefs: BriefSummary[] }>("/api/briefs"),
  /** Full brief for re-hydration: draft + response + cert. */
  get: (briefId: string, opts?: { signal?: AbortSignal }) =>
    api<BriefDetail>(`/api/briefs/${encodeURIComponent(briefId)}`, { signal: opts?.signal }),
  /** Remove a saved brief the user owns. */
  remove: (briefId: string) =>
    api<{ deleted: boolean; brief_id: string }>(`/api/briefs/${encodeURIComponent(briefId)}`, {
      method: "DELETE"
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
  /** Source document id. Null for orphan cards with no concept binding.
   *  When present, click-through on the citation row deep-links to
   *  `/reader/{document_id}?chunk={chunk_id}`. */
  document_id?: string | null;
  /** Chunk id of the most-recent anchor bound to this card. Null when no
   *  anchor exists; the citation row is hidden in that case. */
  chunk_id?: string | null;
  /** 1-indexed page number from the bound anchor. Null when paginating
   *  source doesn't apply (plain-text feeds, manual cards). */
  page_num?: number | null;
  /** Verbatim quote text from the bound anchor. Rendered as the citation
   *  excerpt below the answer body, truncated to ~40 words. */
  quote_text?: string | null;
  /** PR 5.1 (ADR 0002) — render-mode discriminator. "qa" for the legacy
   *  question/answer pair. "cloze" for a sentence with one
   *  `{{cN::term}}` marker shared across both faces (front hides the
   *  term; back reveals it in accent color). PR 5.2 (ADR 0003) — "reverse"
   *  is the swapped twin of a paired qa card; renders identically to qa. */
  kind?: "qa" | "cloze" | "reverse";
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
  /** PR 5.1 (ADR 0002) — render-mode discriminator; see SrsDueCard.kind. */
  kind?: "qa" | "cloze" | "reverse";
}

export interface CardCreatePayload {
  front: string;
  back: string;
  /** Optional. Omit to create an orphan card (shows up in "All subjects"). */
  conceptId?: string;
  /** Optional direct document linkage. Set by the Reader so a manually
   *  authored card remembers which PDF it came from. */
  docId?: string;
  /** Optional override. Defaults to "custom" on the server. */
  cardType?: string;
  /** PR 5.1 — render mode. Omit for legacy qa cards (default). */
  kind?: "qa" | "cloze" | "reverse";
}

export interface CardPairCreatePayload {
  front: string;
  back: string;
  /** Optional. Omit to create an orphan pair (shows up in "All subjects"). */
  conceptId?: string;
  /** Optional direct document linkage. Set by the Reader so a manually
   *  authored card remembers which PDF it came from. */
  docId?: string;
  /** Optional override. Defaults to "custom" on the server. */
  cardType?: string;
}

export interface CardPairCreateResponse {
  primary: SrsCard;
  reverse: SrsCard;
  primary_id: string;
  reverse_id: string;
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
  /**
   * Cards due for review, optionally scoped to one subject or doc.
   * Both filters AND together. Omit both to get the full due queue.
   * Mirrors the filter shape on `listCards` so the Manage view and
   * the Review session share a vocabulary.
   */
  due: (params: { subject?: string | null; docId?: string | null } = {}) => {
    const qs = new URLSearchParams();
    if (params.subject) qs.set("subject", params.subject);
    if (params.docId) qs.set("doc_id", params.docId);
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api<{ cards: SrsDueCard[] }>(`/api/srs/due${suffix}`);
  },
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
        doc_id: payload.docId ?? null,
        card_type: payload.cardType ?? "custom",
        kind: payload.kind ?? "qa"
      }
    }),
  /**
   * Create a reverse-pair from one front/back input. Server inserts a
   * primary qa card AND its swapped reverse twin AND a card_pairs row
   * in one transaction. Each card has independent FSRS state. PR 5.2
   * (ADR 0003).
   */
  createCardPair: (payload: CardPairCreatePayload) =>
    api<CardPairCreateResponse>("/api/srs/cards/pair", {
      method: "POST",
      body: {
        front: payload.front,
        back: payload.back,
        concept_id: payload.conceptId ?? null,
        doc_id: payload.docId ?? null,
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
      },
      timeoutMs: 120_000
    })
};
