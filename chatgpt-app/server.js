import { randomUUID } from "node:crypto";
import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import {
  registerAppResource,
  registerAppTool,
  RESOURCE_MIME_TYPE,
} from "@modelcontextprotocol/ext-apps/server";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StreamableHTTPServerTransport } from "@modelcontextprotocol/sdk/server/streamableHttp.js";
import { isInitializeRequest } from "@modelcontextprotocol/sdk/types.js";
import { z } from "zod";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const widgetUri = "ui://widget/einstein-learning-os-v2.html";
const widgetHtml = readFileSync(
  path.join(__dirname, "public", "einstein-widget.html"),
  "utf8"
);

const PORT = Number(process.env.PORT ?? 8787);
const MCP_PATH = process.env.MCP_PATH ?? "/mcp";
const API_BASE_URL = process.env.EINSTEIN_API_BASE_URL ?? "http://127.0.0.1:8000";
const APP_DOMAIN = process.env.CHATGPT_APP_DOMAIN ?? "";

const apiOrigin = new URL(API_BASE_URL).origin;
const noAuth = [{ type: "noauth" }];

const responseModes = ["standard", "concise", "exam", "socratic"];
const sessionModes = ["focus_sprint", "review", "tutor", "exam_prep", "mixed"];
const workspaceSurfaces = ["tutor", "session", "notes", "review", "concept"];
const reviewRatings = ["again", "hard", "good", "easy"];
const transports = new Map();

const askEinsteinInputSchema = {
  question: z.string().min(1),
  response_mode: z.enum(responseModes).optional(),
  session_id: z.string().optional(),
  goal_id: z.string().optional(),
  source_scope: z.array(z.string()).optional(),
  concept_scope: z.array(z.string()).optional(),
  selected_text: z.string().optional(),
  learner_confidence: z.number().min(0).max(100).optional(),
};

const workspaceInputSchema = {
  surface: z.enum(workspaceSurfaces).optional(),
  goal_id: z.string().optional(),
  source_ids: z.array(z.string()).optional(),
  concept_ids: z.array(z.string()).optional(),
  session_id: z.string().optional(),
};

const learningOsStateInputSchema = {
  ...workspaceInputSchema,
  notes_limit: z.number().int().min(1).max(100).optional(),
  artifacts_limit: z.number().int().min(1).max(50).optional(),
};

const goalInputSchema = {
  goal: z.string().min(1),
};

const startSessionInputSchema = {
  objective: z.string().min(1),
  duration_minutes: z.number().int().min(5).max(180).optional(),
  mode: z.enum(sessionModes).optional(),
  difficulty_target: z.string().optional(),
  goal_id: z.string().optional(),
  source_scope: z.array(z.string()).optional(),
  concept_scope: z.array(z.string()).optional(),
};

const documentDetailInputSchema = {
  doc_id: z.string().min(1),
};

const listNotesInputSchema = {
  doc_id: z.string().optional(),
  concept_id: z.string().optional(),
  limit: z.number().int().min(1).max(100).optional(),
};

const saveNoteInputSchema = {
  note_id: z.string().optional(),
  doc_id: z.string().optional(),
  concept_id: z.string().optional(),
  title: z.string().optional(),
  content: z.string().min(1),
  source_snippet: z.string().optional(),
  note_type: z.string().optional(),
  goal_id: z.string().optional(),
  session_id: z.string().optional(),
  evidence_reference_ids: z.array(z.string()).optional(),
};

const listArtifactsInputSchema = {
  limit: z.number().int().min(1).max(50).optional(),
};

const generateArtifactInputSchema = {
  artifact_kind: z.string().optional(),
  source_scope: z.array(z.string()).optional(),
  concept_scope: z.array(z.string()).optional(),
  goal_id: z.string().optional(),
  session_id: z.string().optional(),
  audience: z.string().optional(),
  difficulty: z.string().optional(),
  depth: z.string().optional(),
  style: z.string().optional(),
  output_length: z.string().optional(),
  evidence_strictness: z.string().optional(),
  custom_prompt: z.string().optional(),
};

const reviewQueueInputSchema = {
  goal_id: z.string().optional(),
  source_ids: z.array(z.string()).optional(),
  session_id: z.string().optional(),
  include_missed: z.boolean().optional(),
};

const reviewCardInputSchema = {
  card_id: z.string().min(1),
  rating: z.enum(reviewRatings),
};

const compareConceptsInputSchema = {
  left_id: z.string().min(1),
  right_id: z.string().min(1),
};

const conceptGraphInputSchema = {
  doc_id: z.string().optional(),
  subject_name: z.string().optional(),
};

const completeSessionInputSchema = {
  session_id: z.string().min(1),
};

function safeArray(value) {
  return Array.isArray(value) ? value : [];
}

function truncate(value, limit = 220) {
  const text = String(value ?? "").trim();
  if (!text) return "";
  if (text.length <= limit) return text;
  return `${text.slice(0, limit - 1)}...`;
}

async function callEinstein(pathname, options = {}) {
  const targetUrl = new URL(pathname, API_BASE_URL);
  const response = await fetch(targetUrl, {
    ...options,
    headers: {
      "content-type": "application/json",
      ...(options.headers || {}),
    },
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail =
      payload?.detail ||
      payload?.message ||
      `${response.status} ${response.statusText}`;
    throw new Error(detail);
  }
  return payload;
}

function buildQuery(pathname, params) {
  const query = params.toString();
  return `${pathname}${query ? `?${query}` : ""}`;
}

function workspaceQuery({
  surface = "tutor",
  goal_id,
  source_ids = [],
  concept_ids = [],
  session_id,
} = {}) {
  const params = new URLSearchParams();
  params.set("surface", surface);
  if (goal_id) params.set("goal_id", goal_id);
  for (const sourceId of safeArray(source_ids)) {
    params.append("source_ids", sourceId);
  }
  for (const conceptId of safeArray(concept_ids)) {
    params.append("concept_ids", conceptId);
  }
  if (session_id) params.set("session_id", session_id);
  return buildQuery("/api/workspace/v2", params);
}

function notesQuery({ doc_id, concept_id, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (doc_id) params.set("doc_id", doc_id);
  if (concept_id) params.set("concept_id", concept_id);
  params.set("limit", String(limit));
  return buildQuery("/api/notes", params);
}

function artifactsQuery({ limit = 12 } = {}) {
  const params = new URLSearchParams();
  params.set("limit", String(limit));
  return buildQuery("/api/studio/artifacts", params);
}

function reviewQueueQuery({
  goal_id,
  source_ids = [],
  session_id,
  include_missed = true,
} = {}) {
  const params = new URLSearchParams();
  if (goal_id) params.set("goal_id", goal_id);
  for (const sourceId of safeArray(source_ids)) {
    params.append("source_ids", sourceId);
  }
  if (session_id) params.set("session_id", session_id);
  params.set("include_missed", include_missed ? "true" : "false");
  return buildQuery("/api/review/queue", params);
}

function conceptGraphQuery({ doc_id, subject_name } = {}) {
  const params = new URLSearchParams();
  if (doc_id) params.set("doc_id", doc_id);
  if (subject_name) params.set("subject_name", subject_name);
  return buildQuery("/api/concepts/graph", params);
}

function normalizeNotes(payload) {
  return safeArray(payload?.notes);
}

function normalizeArtifacts(payload) {
  return safeArray(payload?.artifacts);
}

function normalizeReviewQueue(payload) {
  return safeArray(payload?.items);
}

function normalizeEvidence(payload) {
  return safeArray(payload?.evidence);
}

function createLearningOsState({
  workspace = null,
  documents = [],
  notes = [],
  artifacts = [],
  review = [],
  evidence = [],
  conceptOptions = [],
} = {}) {
  return {
    workspace,
    documents: safeArray(documents),
    notes: safeArray(notes),
    artifacts: safeArray(artifacts),
    review: safeArray(review),
    evidence: safeArray(evidence),
    concept_options: safeArray(conceptOptions),
    hydrated_at: new Date().toISOString(),
  };
}

async function hydrateLearningOsState(args = {}) {
  const [
    workspace,
    documents,
    notesPayload,
    artifactsPayload,
    reviewPayload,
    evidencePayload,
    conceptOptions,
  ] = await Promise.all([
    callEinstein(workspaceQuery(args), {
      headers: { accept: "application/json" },
    }),
    callEinstein("/api/documents", {
      headers: { accept: "application/json" },
    }),
    callEinstein(
      notesQuery({
        limit: args.notes_limit ?? 50,
      }),
      {
        headers: { accept: "application/json" },
      }
    ),
    callEinstein(
      artifactsQuery({
        limit: args.artifacts_limit ?? 12,
      }),
      {
        headers: { accept: "application/json" },
      }
    ),
    callEinstein(
      reviewQueueQuery({
        goal_id: args.goal_id,
        source_ids: args.source_ids,
        session_id: args.session_id,
        include_missed: true,
      }),
      {
        headers: { accept: "application/json" },
      }
    ),
    callEinstein("/api/evidence", {
      headers: { accept: "application/json" },
    }),
    callEinstein("/api/concepts/options", {
      headers: { accept: "application/json" },
    }),
  ]);

  return createLearningOsState({
    workspace,
    documents,
    notes: normalizeNotes(notesPayload),
    artifacts: normalizeArtifacts(artifactsPayload),
    review: normalizeReviewQueue(reviewPayload),
    evidence: normalizeEvidence(evidencePayload),
    conceptOptions,
  });
}

function summarizeWorkspace(workspace) {
  if (!workspace) return null;

  const sources = safeArray(workspace.left_rail?.sources);
  const mastery = safeArray(workspace.mastery);
  const evidence = safeArray(workspace.right_rail?.evidence);
  const sessions = safeArray(workspace.left_rail?.sessions);
  const notes = safeArray(workspace.left_rail?.notes);
  const artifacts = safeArray(workspace.left_rail?.artifacts);
  const nextAction =
    workspace.next_action || workspace.right_rail?.next_actions?.[0] || null;
  const activeExchange = workspace.center_canvas?.payload?.active_exchange || null;

  return {
    goal: workspace.goal || "",
    surface: workspace.scope?.surface || "tutor",
    momentum: {
      headline: workspace.momentum?.headline || "",
      reason: workspace.momentum?.reason || "",
      focus_concept_name: workspace.momentum?.focus_concept_name || null,
    },
    counts: {
      sources: sources.length,
      notes: notes.length,
      artifacts: artifacts.length,
      sessions: sessions.length,
      mastery_items: mastery.length,
      evidence: evidence.length,
    },
    next_action: nextAction
      ? {
          label: nextAction.label || nextAction.type || "Next action",
          type: nextAction.type || null,
          concept_id: nextAction.concept_id || null,
        }
      : null,
    sources: sources.slice(0, 4).map((item) => ({
      id: item.id,
      filename: item.filename,
      subject_name: item.subject_name || "",
      concept_count: item.concept_count || 0,
    })),
    mastery: mastery.slice(0, 4).map((item) => ({
      id: item.id,
      name: item.name,
      mastery: item.mastery,
      band: item.band,
      due_cards: item.due_cards,
    })),
    active_exchange: activeExchange
      ? {
          question: truncate(activeExchange.question, 120),
          answer: truncate(activeExchange.answer, 220),
        }
      : null,
  };
}

function summarizeDocuments(documents) {
  return safeArray(documents).slice(0, 6).map((item) => ({
    id: item.id,
    filename: item.filename,
    subject_name: item.subject_name || "",
    status: item.status || "",
    concept_count: item.concept_count ?? 0,
    question_count: item.question_count ?? 0,
    summary: truncate(item.summary, 140),
  }));
}

function summarizeNotes(notes) {
  return safeArray(notes).slice(0, 6).map((item) => ({
    id: item.id,
    title: item.title || "Untitled note",
    concept_name: item.concept_name || null,
    document_name: item.document_name || null,
    note_type: item.note_type || null,
    excerpt: truncate(item.content || item.source_snippet || "", 140),
    updated_at: item.updated_at || item.created_at || null,
  }));
}

function summarizeArtifacts(artifacts) {
  return safeArray(artifacts).slice(0, 6).map((item) => ({
    id: item.id,
    artifact_kind: item.artifact_kind || "",
    status: item.status || "",
    stale: Boolean(item.stale),
    preview: truncate(item.preview || item.output_markdown || "", 140),
    updated_at: item.updated_at || item.created_at || null,
  }));
}

function summarizeReviewQueue(items) {
  return safeArray(items).slice(0, 6).map((item) => ({
    id: item.id,
    concept_name: item.concept_name || "",
    source_name: item.source_name || "",
    state: item.state || "",
    due_date: item.due_date || null,
    missed_recently: Boolean(item.missed_recently),
  }));
}

function summarizeConceptOptions(options) {
  return safeArray(options).slice(0, 8).map((item) => ({
    id: item.id,
    name: item.name || item.raw_name || "",
    document_name: item.document_name || "",
  }));
}

function summarizeTutorResponse(tutor) {
  if (!tutor) return null;

  return {
    answer: truncate(tutor.answer, 420),
    citations: safeArray(tutor.citations).map((item) => ({
      label: item.label || item.document_name || "Source",
      source_id: item.source_id || null,
    })),
    evidence: safeArray(tutor.evidence).slice(0, 5).map((item) => ({
      id: item.id || "",
      label: item.label || item.document_name || "Evidence",
      excerpt: truncate(item.anchor_text || item.excerpt || "", 160),
      document_name: item.document_name || "",
      page_num: item.page_num || null,
    })),
    misconceptions: safeArray(tutor.misconceptions).slice(0, 4),
    scaffolds: safeArray(tutor.scaffolds).slice(0, 4),
    actions: safeArray(tutor.actions).slice(0, 4),
    exchange_id: tutor.exchange_id || null,
  };
}

function summarizeSession(session) {
  if (!session) return null;
  return {
    id: session.id || session.session_id || null,
    objective: session.objective || "",
    mode: session.mode || "",
    duration_minutes: session.duration_minutes || null,
    status: session.status || "",
  };
}

function summarizeDocumentDetail(detail) {
  if (!detail) return null;
  return {
    document: detail.document
      ? {
          id: detail.document.id,
          filename: detail.document.filename,
          subject_name: detail.document.subject_name || "",
          status: detail.document.status || "",
          page_count: detail.document.page_count || 0,
        }
      : null,
    summary: truncate(detail.summary, 220),
    counts: {
      chunks: detail.counts?.chunks ?? safeArray(detail.chunks).length,
      concepts: detail.counts?.concepts ?? safeArray(detail.concepts).length,
      questions: detail.counts?.questions ?? safeArray(detail.questions).length,
      cards: detail.counts?.cards ?? 0,
    },
    concepts: safeArray(detail.concepts).slice(0, 6).map((item) => ({
      id: item.id,
      name: item.display_name || item.name || "",
      mastery: item.mastery ?? 0,
    })),
    questions: safeArray(detail.questions).slice(0, 4).map((item) => ({
      id: item.id,
      question: truncate(item.question, 120),
      concept: item.concept || item.raw_concept || "",
    })),
  };
}

function summarizeComparison(comparison) {
  if (!comparison) return null;
  return {
    left: comparison.left
      ? {
          id: comparison.left.id,
          name: comparison.left.name || comparison.left.raw_name || "",
        }
      : null,
    right: comparison.right
      ? {
          id: comparison.right.id,
          name: comparison.right.name || comparison.right.raw_name || "",
        }
      : null,
    similarities: safeArray(comparison.similarities).slice(0, 4),
    differences: safeArray(comparison.differences).slice(0, 4),
    study_prompt: truncate(comparison.study_prompt, 200),
  };
}

function summarizeConceptGraph(graph) {
  if (!graph) return null;
  const nodes = safeArray(graph.nodes);
  const edges = safeArray(graph.edges);
  const nodeLabels = new Map(
    nodes.map((item) => [item.id, item.label || item.raw_label || item.id])
  );

  return {
    counts: {
      nodes: nodes.length,
      edges: edges.length,
    },
    nodes: nodes.slice(0, 8).map((item) => ({
      id: item.id,
      label: item.label || item.raw_label || "",
      mastery: item.mastery ?? 0,
      document_name: item.document_name || "",
    })),
    edges: edges.slice(0, 8).map((item) => ({
      source: nodeLabels.get(item.source) || item.source,
      target: nodeLabels.get(item.target) || item.target,
      relationship: item.relationship || "related",
    })),
  };
}

function summarizeCompletion(completion) {
  if (!completion) return null;
  return {
    mastery_delta: completion.mastery_delta ?? null,
    due_queue_count: completion.due_queue_count ?? null,
    weak_concepts: safeArray(completion.weak_concepts).slice(0, 4),
    generated_cards: completion.generated_cards ?? null,
    revision_recommendation: truncate(completion.revision_recommendation, 180),
    suggested_next_session: truncate(completion.suggested_next_session, 180),
  };
}

function summarizeLearningOsState(learningOsState) {
  if (!learningOsState) return null;

  const workspace = learningOsState.workspace || null;
  const sources = safeArray(workspace?.left_rail?.sources);
  const rawDocuments = safeArray(learningOsState.documents);
  const documents = rawDocuments.length ? rawDocuments : sources;
  const rawNotes = safeArray(learningOsState.notes);
  const notes = rawNotes.length ? rawNotes : safeArray(workspace?.left_rail?.notes);
  const rawArtifacts = safeArray(learningOsState.artifacts);
  const artifacts = rawArtifacts.length
    ? rawArtifacts
    : safeArray(workspace?.left_rail?.artifacts);
  const rawReview = safeArray(learningOsState.review);
  const review = rawReview.length ? rawReview : [];
  const rawEvidence = safeArray(learningOsState.evidence);
  const evidence = rawEvidence.length
    ? rawEvidence
    : safeArray(workspace?.right_rail?.evidence);
  const rawConceptOptions = safeArray(learningOsState.concept_options);
  const conceptOptions = rawConceptOptions.length
    ? rawConceptOptions
    : safeArray(workspace?.compatibility?.compareOptions);
  const sessions = safeArray(workspace?.left_rail?.sessions);
  const mastery = safeArray(workspace?.mastery);
  const activeSession =
    sessions.find((item) => item.status === "active") ||
    workspace?.center_canvas?.payload?.session ||
    null;
  const activeExchange = workspace?.center_canvas?.payload?.active_exchange || null;
  const nextAction =
    workspace?.next_action || workspace?.right_rail?.next_actions?.[0] || null;

  return {
    goal: workspace?.goal || "",
    surface: workspace?.scope?.surface || "tutor",
    momentum: {
      headline: workspace?.momentum?.headline || "",
      reason: workspace?.momentum?.reason || "",
      focus_concept_name: workspace?.momentum?.focus_concept_name || null,
    },
    counts: {
      documents: documents.length,
      notes: notes.length,
      artifacts: artifacts.length,
      review_items: review.length,
      evidence: evidence.length,
      concepts: conceptOptions.length,
      sessions: sessions.length,
      mastery_items: mastery.length,
    },
    next_action: nextAction
      ? {
          label: nextAction.label || nextAction.type || "Next action",
          type: nextAction.type || null,
          concept_id: nextAction.concept_id || null,
        }
      : null,
    active_session: summarizeSession(activeSession),
    active_exchange: activeExchange
      ? {
          question: truncate(activeExchange.question, 120),
          answer: truncate(activeExchange.answer, 220),
          model_confidence:
            workspace?.right_rail?.confidence?.model ??
            activeExchange.model_confidence ??
            null,
        }
      : null,
    documents: summarizeDocuments(documents).slice(0, 3),
    notes: summarizeNotes(notes).slice(0, 3),
    artifacts: summarizeArtifacts(artifacts).slice(0, 3),
    review: summarizeReviewQueue(review).slice(0, 3),
    concepts: summarizeConceptOptions(conceptOptions).slice(0, 6),
  };
}

function buildWidgetResult({
  message,
  learningOsState = null,
  workspace = null,
  tutor = null,
  session = null,
  goal = null,
  documents = null,
  documentDetail = null,
  notes = null,
  note = null,
  artifacts = null,
  artifact = null,
  reviewQueue = null,
  reviewResult = null,
  comparison = null,
  conceptGraph = null,
  completion = null,
  error = null,
}) {
  const effectiveLearningOsState =
    learningOsState ||
    (workspace
      ? createLearningOsState({
          workspace,
          documents: documents ?? safeArray(workspace?.left_rail?.sources),
          notes: notes ?? safeArray(workspace?.left_rail?.notes),
          artifacts: artifacts ?? safeArray(workspace?.left_rail?.artifacts),
          review: reviewQueue ?? [],
          evidence: safeArray(workspace?.right_rail?.evidence),
          conceptOptions: safeArray(workspace?.compatibility?.compareOptions),
        })
      : null);

  return {
    content: message ? [{ type: "text", text: message }] : [],
    structuredContent: {
      widget: {
        status: error ? "error" : "ok",
        learning_os_state: summarizeLearningOsState(effectiveLearningOsState),
        workspace: summarizeWorkspace(workspace || effectiveLearningOsState?.workspace),
        tutor: summarizeTutorResponse(tutor),
        session: summarizeSession(session),
        goal: goal ? { goal: goal.goal || goal.title || "" } : null,
        documents: documents ? summarizeDocuments(documents) : null,
        document_detail: summarizeDocumentDetail(documentDetail),
        notes: notes ? summarizeNotes(notes) : null,
        note: note
          ? {
              id: note.id || null,
              title: note.title || "Untitled note",
              concept_name: note.concept_name || null,
              excerpt: truncate(note.content || note.source_snippet || "", 180),
            }
          : null,
        artifacts: artifacts ? summarizeArtifacts(artifacts) : null,
        artifact: artifact
          ? {
              id: artifact.id || null,
              artifact_kind: artifact.artifact_kind || "",
              status: artifact.status || "",
              stale: Boolean(artifact.stale),
              preview: truncate(
                artifact.output_markdown || artifact.preview || "",
                200
              ),
            }
          : null,
        review_queue: reviewQueue ? summarizeReviewQueue(reviewQueue) : null,
        review_result: reviewResult
          ? {
              next_due_date: reviewResult.next_due_date || null,
              interval: reviewResult.interval || null,
              ease: reviewResult.ease || null,
            }
          : null,
        comparison: summarizeComparison(comparison),
        concept_graph: summarizeConceptGraph(conceptGraph),
        completion: summarizeCompletion(completion),
        error: error ? { message: error.message || String(error) } : null,
      },
    },
    _meta: {
      widget: {
        learning_os_state: effectiveLearningOsState,
        workspace,
        tutor,
        session,
        goal,
        documents,
        document_detail: documentDetail,
        notes,
        note,
        artifacts,
        artifact,
        review_queue: reviewQueue,
        review_result: reviewResult,
        comparison,
        concept_graph: conceptGraph,
        completion,
        error: error ? { message: error.message || String(error) } : null,
        api_base_url: API_BASE_URL,
      },
    },
  };
}

function errorResult(message, error) {
  return buildWidgetResult({
    message,
    error: {
      message: error?.message || String(error || "Unknown error"),
    },
  });
}

function headerValue(value) {
  if (Array.isArray(value)) return value[0];
  return value;
}

function widgetToolMeta(invoking, invoked) {
  return {
    securitySchemes: noAuth,
    ui: { resourceUri: widgetUri },
    "openai/toolInvocation/invoking": invoking,
    "openai/toolInvocation/invoked": invoked,
  };
}

function sendJsonRpcError(res, status, message, code = -32000) {
  if (res.headersSent) return;
  res.writeHead(status, { "content-type": "application/json; charset=utf-8" });
  res.end(
    JSON.stringify({
      jsonrpc: "2.0",
      error: { code, message },
      id: null,
    })
  );
}

async function readJsonBody(req) {
  const chunks = [];
  for await (const chunk of req) {
    chunks.push(Buffer.isBuffer(chunk) ? chunk : Buffer.from(chunk));
  }
  if (!chunks.length) return undefined;
  const raw = Buffer.concat(chunks).toString("utf8").trim();
  if (!raw) return undefined;
  return JSON.parse(raw);
}

async function createSessionTransport() {
  const server = createEinsteinServer();
  let transport;
  transport = new StreamableHTTPServerTransport({
    sessionIdGenerator: () => randomUUID(),
    enableJsonResponse: true,
    onsessioninitialized: (sessionId) => {
      transports.set(sessionId, transport);
    },
  });
  transport.onclose = () => {
    const sessionId = transport.sessionId;
    if (sessionId) {
      transports.delete(sessionId);
    }
    void server.close();
  };
  await server.connect(transport);
  return transport;
}

function createEinsteinServer() {
  const server = new McpServer({ name: "einstein-chatgpt-app", version: "0.2.1" });

  registerAppResource(
    server,
    "einstein-widget",
    widgetUri,
    {},
    async () => ({
      contents: [
        {
          uri: widgetUri,
          mimeType: RESOURCE_MIME_TYPE,
          text: widgetHtml,
          _meta: {
            ui: {
              prefersBorder: true,
              csp: {
                connectDomains: [apiOrigin],
                resourceDomains: [],
              },
              ...(APP_DOMAIN ? { domain: APP_DOMAIN } : {}),
            },
            "openai/widgetDescription":
              "Einstein is a learning OS widget with dashboard, session, tutor, source, notes, artifact, review, and concept graph surfaces backed by the local Einstein API.",
            "openai/widgetPrefersBorder": true,
            "openai/widgetCSP": {
              connect_domains: [apiOrigin],
              resource_domains: [],
            },
            ...(APP_DOMAIN ? { "openai/widgetDomain": APP_DOMAIN } : {}),
          },
        },
      ],
    })
  );

  registerAppTool(
    server,
    "get_learning_os_state",
    {
      title: "Hydrate learning OS state",
      description:
        "Loads the full Einstein widget payload: workspace, documents, notes, artifacts, review queue, evidence, and concept options.",
      inputSchema: learningOsStateInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Hydrating Einstein...", "Einstein ready"),
    },
    async (args = {}) => {
      try {
        const learningOsState = await hydrateLearningOsState(args);
        return buildWidgetResult({
          message: `Hydrated Einstein${learningOsState.workspace?.goal ? ` for "${learningOsState.workspace.goal}"` : ""}.`,
          learningOsState,
        });
      } catch (error) {
        return errorResult(
          `I could not hydrate the Einstein learning OS from ${API_BASE_URL}. Make sure the FastAPI app is running first.`,
          error
        );
      }
    }
  );

  registerAppTool(
    server,
    "get_workspace_overview",
    {
      title: "Get workspace overview",
      description:
        "Loads Einstein's current goal, momentum, sources, mastery, and next best action.",
      inputSchema: workspaceInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading workspace...", "Workspace ready"),
    },
    async (args = {}) => {
      try {
        const workspace = await callEinstein(workspaceQuery(args), {
          headers: { accept: "application/json" },
        });
        return buildWidgetResult({
          message: `Loaded Einstein workspace${workspace.goal ? ` for "${workspace.goal}"` : ""}.`,
          workspace,
        });
      } catch (error) {
        return errorResult(
          `I could not load the Einstein workspace from ${API_BASE_URL}. Make sure the FastAPI app is running first.`,
          error
        );
      }
    }
  );

  registerAppTool(
    server,
    "set_learning_goal",
    {
      title: "Set learning goal",
      description: "Updates Einstein's current workspace goal.",
      inputSchema: goalInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Saving goal...", "Goal saved"),
    },
    async (args = {}) => {
      try {
        await callEinstein("/api/goal", {
          method: "POST",
          body: JSON.stringify({ goal: args.goal }),
        });
        const learningOsState = await hydrateLearningOsState({ surface: "tutor" });
        return buildWidgetResult({
          message: `Updated Einstein's goal to "${learningOsState.workspace?.goal || args.goal}".`,
          learningOsState,
          goal: { goal: learningOsState.workspace?.goal || args.goal },
        });
      } catch (error) {
        return errorResult("I could not update the learning goal.", error);
      }
    }
  );

  registerAppTool(
    server,
    "ask_einstein",
    {
      title: "Ask Einstein",
      description:
        "Sends a grounded tutor question to Einstein and returns evidence-backed guidance.",
      inputSchema: askEinsteinInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Einstein is thinking...", "Answer ready"),
    },
    async (args = {}) => {
      try {
        const tutor = await callEinstein("/api/tutor/exchanges", {
          method: "POST",
          body: JSON.stringify({
            question: args.question,
            session_id: args.session_id ?? null,
            goal_id: args.goal_id ?? null,
            source_scope: safeArray(args.source_scope),
            concept_scope: safeArray(args.concept_scope),
            selected_text: args.selected_text ?? null,
            learner_confidence: args.learner_confidence ?? null,
            mode: "tutor",
            response_mode: args.response_mode ?? "standard",
            depth: "standard",
            evidence_strictness: "citation-heavy",
          }),
        });
        const workspace = await callEinstein(
          workspaceQuery({
            surface: "tutor",
            goal_id: args.goal_id,
            source_ids: args.source_scope,
            concept_ids: args.concept_scope,
            session_id: args.session_id,
          })
        );
        return buildWidgetResult({
          message: tutor.answer || "Einstein answered your question.",
          workspace,
          tutor,
        });
      } catch (error) {
        return errorResult("I could not get an answer from Einstein.", error);
      }
    }
  );

  registerAppTool(
    server,
    "start_study_session",
    {
      title: "Start study session",
      description:
        "Starts a focused Einstein study session with a goal, duration, and optional source or concept scope.",
      inputSchema: startSessionInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Starting session...", "Session started"),
    },
    async (args = {}) => {
      try {
        const session = await callEinstein("/api/sessions", {
          method: "POST",
          body: JSON.stringify({
            objective: args.objective,
            duration_minutes: args.duration_minutes ?? 20,
            mode: args.mode ?? "focus_sprint",
            difficulty_target: args.difficulty_target ?? "standard",
            goal_id: args.goal_id ?? null,
            source_scope: safeArray(args.source_scope),
            concept_scope: safeArray(args.concept_scope),
          }),
        });
        const workspace = await callEinstein(
          workspaceQuery({
            surface: "session",
            goal_id: args.goal_id,
            source_ids: args.source_scope,
            concept_ids: args.concept_scope,
            session_id: session.id ?? session.session_id ?? null,
          })
        );
        return buildWidgetResult({
          message: `Started a ${session.mode || args.mode || "focus"} session for "${session.objective || args.objective}".`,
          workspace,
          session,
        });
      } catch (error) {
        return errorResult("I could not start the study session.", error);
      }
    }
  );

  registerAppTool(
    server,
    "list_documents",
    {
      title: "List documents",
      description: "Lists the study sources available in Einstein.",
      inputSchema: {},
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading sources...", "Sources ready"),
    },
    async () => {
      try {
        const documents = safeArray(
          await callEinstein("/api/documents", {
            headers: { accept: "application/json" },
          })
        );
        return buildWidgetResult({
          message: `Loaded ${documents.length} source${documents.length === 1 ? "" : "s"}.`,
          documents,
        });
      } catch (error) {
        return errorResult("I could not load the source library.", error);
      }
    }
  );

  registerAppTool(
    server,
    "get_document_detail",
    {
      title: "Get document detail",
      description:
        "Loads a source's summary, concepts, questions, and chunk-level detail for the materials view.",
      inputSchema: documentDetailInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading source detail...", "Source detail ready"),
    },
    async (args = {}) => {
      try {
        const documentDetail = await callEinstein(
          `/api/documents/${encodeURIComponent(args.doc_id)}`,
          {
            headers: { accept: "application/json" },
          }
        );
        return buildWidgetResult({
          message: `Loaded detail for "${documentDetail.document?.filename || "source"}".`,
          documentDetail,
        });
      } catch (error) {
        return errorResult("I could not load that source detail.", error);
      }
    }
  );

  registerAppTool(
    server,
    "list_notes",
    {
      title: "List notes",
      description: "Lists notes for the notes workbench.",
      inputSchema: listNotesInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading notes...", "Notes ready"),
    },
    async (args = {}) => {
      try {
        const payload = await callEinstein(notesQuery(args), {
          headers: { accept: "application/json" },
        });
        const notes = normalizeNotes(payload);
        return buildWidgetResult({
          message: `Loaded ${notes.length} note${notes.length === 1 ? "" : "s"}.`,
          notes,
        });
      } catch (error) {
        return errorResult("I could not load notes.", error);
      }
    }
  );

  registerAppTool(
    server,
    "save_note",
    {
      title: "Save note",
      description:
        "Creates or updates a note, then refreshes the note list and workspace context.",
      inputSchema: saveNoteInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Saving note...", "Note saved"),
    },
    async (args = {}) => {
      try {
        const saveResult = await callEinstein("/api/notes", {
          method: "POST",
          body: JSON.stringify({
            note_id: args.note_id ?? null,
            doc_id: args.doc_id ?? null,
            concept_id: args.concept_id ?? null,
            title: args.title ?? null,
            content: args.content,
            source_snippet: args.source_snippet ?? null,
            note_type: args.note_type ?? "saved_insight",
            goal_id: args.goal_id ?? null,
            session_id: args.session_id ?? null,
            evidence_reference_ids: safeArray(args.evidence_reference_ids),
          }),
        });
        const [notesPayload, workspace] = await Promise.all([
          callEinstein(
            notesQuery({
              limit: 50,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
          callEinstein(
            workspaceQuery({
              surface: "notes",
              goal_id: args.goal_id,
              source_ids: args.doc_id ? [args.doc_id] : [],
              concept_ids: args.concept_id ? [args.concept_id] : [],
              session_id: args.session_id,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
        ]);

        return buildWidgetResult({
          message: `Saved note${saveResult.note?.title ? ` "${saveResult.note.title}"` : ""}.`,
          workspace,
          notes: normalizeNotes(notesPayload),
          note: saveResult.note || null,
        });
      } catch (error) {
        return errorResult("I could not save the note.", error);
      }
    }
  );

  registerAppTool(
    server,
    "list_artifacts",
    {
      title: "List artifacts",
      description: "Lists generated study artifacts for the artifacts view.",
      inputSchema: listArtifactsInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading artifacts...", "Artifacts ready"),
    },
    async (args = {}) => {
      try {
        const payload = await callEinstein(
          artifactsQuery({
            limit: args.limit ?? 12,
          }),
          {
            headers: { accept: "application/json" },
          }
        );
        const artifacts = normalizeArtifacts(payload);
        return buildWidgetResult({
          message: `Loaded ${artifacts.length} artifact${artifacts.length === 1 ? "" : "s"}.`,
          artifacts,
        });
      } catch (error) {
        return errorResult("I could not load artifacts.", error);
      }
    }
  );

  registerAppTool(
    server,
    "generate_artifact",
    {
      title: "Generate artifact",
      description:
        "Creates a new study artifact and refreshes the artifact list and workspace context.",
      inputSchema: generateArtifactInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Generating artifact...", "Artifact ready"),
    },
    async (args = {}) => {
      try {
        const artifactPayload = await callEinstein("/api/studio/generate", {
          method: "POST",
          body: JSON.stringify({
            artifact_kind: args.artifact_kind ?? "study_guide",
            source_scope: safeArray(args.source_scope),
            concept_scope: safeArray(args.concept_scope),
            goal_id: args.goal_id ?? null,
            session_id: args.session_id ?? null,
            audience: args.audience ?? "student",
            difficulty: args.difficulty ?? "standard",
            depth: args.depth ?? "standard",
            style: args.style ?? "prose",
            output_length: args.output_length ?? "medium",
            evidence_strictness: args.evidence_strictness ?? "normal",
            custom_prompt: args.custom_prompt ?? null,
          }),
        });
        const [artifactsPayload, workspace] = await Promise.all([
          callEinstein(
            artifactsQuery({
              limit: 12,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
          callEinstein(
            workspaceQuery({
              surface: "tutor",
              goal_id: args.goal_id,
              source_ids: args.source_scope,
              concept_ids: args.concept_scope,
              session_id: args.session_id,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
        ]);

        return buildWidgetResult({
          message: `Generated ${artifactPayload.artifact?.artifact_kind || args.artifact_kind || "artifact"}.`,
          workspace,
          artifacts: normalizeArtifacts(artifactsPayload),
          artifact: artifactPayload.artifact || null,
        });
      } catch (error) {
        return errorResult("I could not generate an artifact.", error);
      }
    }
  );

  registerAppTool(
    server,
    "get_review_queue",
    {
      title: "Get review queue",
      description: "Loads the adaptive review queue for due cards.",
      inputSchema: reviewQueueInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading review queue...", "Review queue ready"),
    },
    async (args = {}) => {
      try {
        const payload = await callEinstein(reviewQueueQuery(args), {
          headers: { accept: "application/json" },
        });
        const reviewQueue = normalizeReviewQueue(payload);
        return buildWidgetResult({
          message: `Loaded ${reviewQueue.length} review item${reviewQueue.length === 1 ? "" : "s"}.`,
          reviewQueue,
        });
      } catch (error) {
        return errorResult("I could not load the review queue.", error);
      }
    }
  );

  registerAppTool(
    server,
    "review_card",
    {
      title: "Review card",
      description:
        "Scores a review card and refreshes the review queue and review-oriented workspace context.",
      inputSchema: reviewCardInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Saving review...", "Review saved"),
    },
    async (args = {}) => {
      try {
        const reviewResult = await callEinstein("/api/srs/review", {
          method: "POST",
          body: JSON.stringify({
            card_id: args.card_id,
            rating: args.rating,
          }),
        });
        const [reviewPayload, workspace] = await Promise.all([
          callEinstein(
            reviewQueueQuery({
              include_missed: true,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
          callEinstein(
            workspaceQuery({
              surface: "review",
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
        ]);

        return buildWidgetResult({
          message: `Logged "${args.rating}" for the review card.`,
          workspace,
          reviewQueue: normalizeReviewQueue(reviewPayload),
          reviewResult,
        });
      } catch (error) {
        return errorResult("I could not save the review result.", error);
      }
    }
  );

  registerAppTool(
    server,
    "compare_concepts",
    {
      title: "Compare concepts",
      description:
        "Compares two concepts so the widget can show similarities, differences, and a study prompt.",
      inputSchema: compareConceptsInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Comparing concepts...", "Comparison ready"),
    },
    async (args = {}) => {
      try {
        const comparison = await callEinstein("/api/compare", {
          method: "POST",
          body: JSON.stringify({
            left_id: args.left_id,
            right_id: args.right_id,
          }),
        });
        return buildWidgetResult({
          message: `Compared "${comparison.left?.name || "left concept"}" and "${comparison.right?.name || "right concept"}".`,
          comparison,
        });
      } catch (error) {
        return errorResult("I could not compare those concepts.", error);
      }
    }
  );

  registerAppTool(
    server,
    "get_concept_graph",
    {
      title: "Get concept graph",
      description:
        "Loads the concept graph for a document or subject so the widget can show graph summaries without hydrating the whole app again.",
      inputSchema: conceptGraphInputSchema,
      annotations: { readOnlyHint: true },
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Loading concept graph...", "Concept graph ready"),
    },
    async (args = {}) => {
      try {
        const conceptGraph = await callEinstein(conceptGraphQuery(args), {
          headers: { accept: "application/json" },
        });
        return buildWidgetResult({
          message: `Loaded concept graph with ${safeArray(conceptGraph.nodes).length} nodes.`,
          conceptGraph,
        });
      } catch (error) {
        return errorResult("I could not load the concept graph.", error);
      }
    }
  );

  registerAppTool(
    server,
    "complete_study_session",
    {
      title: "Complete study session",
      description:
        "Completes an active Einstein study session and returns post-session recommendations.",
      inputSchema: completeSessionInputSchema,
      securitySchemes: noAuth,
      _meta: widgetToolMeta("Completing session...", "Session completed"),
    },
    async (args = {}) => {
      try {
        const completion = await callEinstein(
          `/api/sessions/${encodeURIComponent(args.session_id)}/complete`,
          {
            method: "POST",
          }
        );
        const [workspace, reviewPayload] = await Promise.all([
          callEinstein(
            workspaceQuery({
              surface: "session",
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
          callEinstein(
            reviewQueueQuery({
              include_missed: true,
            }),
            {
              headers: { accept: "application/json" },
            }
          ),
        ]);

        return buildWidgetResult({
          message: "Completed the study session.",
          workspace,
          reviewQueue: normalizeReviewQueue(reviewPayload),
          completion,
        });
      } catch (error) {
        return errorResult("I could not complete the study session.", error);
      }
    }
  );

  return server;
}

const httpServer = createServer(async (req, res) => {
  if (!req.url) {
    res.writeHead(400).end("Missing URL");
    return;
  }

  const url = new URL(req.url, `http://${req.headers.host ?? "localhost"}`);

  if (req.method === "OPTIONS" && url.pathname.startsWith(MCP_PATH)) {
    res.writeHead(204, {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "POST, GET, DELETE, OPTIONS",
      "Access-Control-Allow-Headers": "content-type, mcp-session-id",
      "Access-Control-Expose-Headers": "Mcp-Session-Id",
    });
    res.end();
    return;
  }

  if (req.method === "GET" && url.pathname === "/") {
    res.writeHead(200, { "content-type": "text/plain; charset=utf-8" });
    res.end("Einstein ChatGPT app MCP server");
    return;
  }

  if (req.method === "GET" && url.pathname === "/health") {
    res.writeHead(200, { "content-type": "application/json; charset=utf-8" });
    res.end(
      JSON.stringify({
        ok: true,
        mcp_path: MCP_PATH,
        api_base_url: API_BASE_URL,
      })
    );
    return;
  }

  if (req.method === "GET" && url.pathname === "/widget-preview") {
    res.writeHead(200, { "content-type": "text/html; charset=utf-8" });
    res.end(widgetHtml);
    return;
  }

  if (
    url.pathname === "/.well-known/oauth-authorization-server" ||
    url.pathname === "/.well-known/openid-configuration"
  ) {
    res.writeHead(404).end("Not Found");
    return;
  }

  const mcpMethods = new Set(["POST", "GET", "DELETE"]);
  if (url.pathname.startsWith(MCP_PATH) && req.method && mcpMethods.has(req.method)) {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Expose-Headers", "Mcp-Session-Id");

    if (req.method === "GET") {
      res.writeHead(405, {
        Allow: "POST, DELETE",
        "content-type": "text/plain; charset=utf-8",
      });
      res.end("Method Not Allowed");
      return;
    }

    if (req.method === "DELETE") {
      const sessionId = headerValue(req.headers["mcp-session-id"]);
      const transport = sessionId ? transports.get(sessionId) : null;
      if (!transport) {
        sendJsonRpcError(res, 400, "Bad Request: No valid session ID provided");
        return;
      }
      try {
        await transport.handleRequest(req, res);
      } catch (error) {
        console.error("Error handling MCP DELETE request:", error);
        if (!res.headersSent) {
          sendJsonRpcError(res, 500, "Internal server error", -32603);
        }
      }
      return;
    }

    let parsedBody;
    try {
      parsedBody = await readJsonBody(req);
    } catch (error) {
      sendJsonRpcError(res, 400, "Bad Request: Invalid JSON body", -32700);
      return;
    }

    const sessionId = headerValue(req.headers["mcp-session-id"]);
    let transport = sessionId ? transports.get(sessionId) : null;
    let createdHere = false;

    try {
      if (!transport) {
        if (sessionId || !isInitializeRequest(parsedBody)) {
          sendJsonRpcError(res, 400, "Bad Request: No valid session ID provided");
          return;
        }
        transport = await createSessionTransport();
        createdHere = true;
      }

      await transport.handleRequest(req, res, parsedBody);
    } catch (error) {
      console.error("Error handling MCP POST request:", error);
      if (createdHere) {
        await transport?.close().catch(() => {});
      }
      if (!res.headersSent) {
        sendJsonRpcError(res, 500, "Internal server error", -32603);
      }
    }
    return;
  }

  res.writeHead(404, { "content-type": "text/plain; charset=utf-8" });
  res.end("Not Found");
});

httpServer.listen(PORT, "127.0.0.1", () => {
  console.log(
    `Einstein ChatGPT app listening on http://127.0.0.1:${PORT}${MCP_PATH}`
  );
  console.log(`Widget preview: http://127.0.0.1:${PORT}/widget-preview`);
  console.log(`Proxying Einstein API calls to ${API_BASE_URL}`);
});
