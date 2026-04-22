async function api(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}));
    throw new Error(payload.detail || "Request failed");
  }
  return response.json();
}

export { api };

export const fetchWorkspace = () => api("/api/workspace");
export const fetchWorkspaceV2 = (query = "") => api(`/api/workspace/v2${query ? `?${query}` : ""}`);
export const fetchBootstrap = () => api("/api/bootstrap");
export const fetchConceptGraph = (suffix = "") => api(`/api/concepts/graph${suffix}`);
export const fetchConceptExplanation = (conceptId, level) => api(`/api/concepts/${conceptId}/explain?level=${level}`);
export const fetchDocument = (docId) => api(`/api/documents/${docId}`);
export const fetchNotes = (query) => api(`/api/notes?${query}`);
export const startDialogueSession = (conceptId) =>
  api("/api/dialogue/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ concept_id: conceptId })
  });
export const sendDialogueMessage = (sessionId, conceptId, message) =>
  api("/api/dialogue/message", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, concept_id: conceptId, message })
  });
export const saveGoalRequest = (goal) =>
  api("/api/goal", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ goal })
  });
export const logEventRequest = (payload) =>
  api("/api/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const tutorQueryRequest = (payload) =>
  api("/api/tutor/query", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const createTutorExchangeRequest = (payload) =>
  api("/api/tutor/exchanges", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const evaluateTutorExchangeRequest = (exchangeId, payload) =>
  api(`/api/tutor/exchanges/${exchangeId}/evaluate`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const saveNoteRequest = (payload) =>
  api("/api/notes", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const transformNoteRequest = (payload) =>
  api("/api/notes/transform", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const saveDocumentSubjectRequest = (docId, subjectName) =>
  api(`/api/documents/${docId}/subject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ subject_name: subjectName })
  });
export const compareConceptsRequest = (leftId, rightId) =>
  api("/api/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ left_id: leftId, right_id: rightId })
  });
export const reviewCardRequest = (cardId, rating) =>
  api("/api/srs/review", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ card_id: cardId, rating })
  });
export const fetchReviewQueueRequest = (query = "") => api(`/api/review/queue${query ? `?${query}` : ""}`);
export const reviewEventRequest = (payload) =>
  api("/api/review/events", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const createSessionRequest = (payload) =>
  api("/api/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const completeSessionRequest = (sessionId) =>
  api(`/api/sessions/${sessionId}/complete`, {
    method: "POST"
  });
export const uploadDocumentRequest = (formData) =>
  api("/api/documents/upload", {
    method: "POST",
    body: formData
  });
export const deleteDocumentRequest = (docId) =>
  api(`/api/documents/${docId}`, {
    method: "DELETE"
  });

// ── Studio ────────────────────────────────────────────────────────────────────
export const generateArtifactRequest = (payload) =>
  api("/api/studio/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const listArtifactsRequest = (limit = 10) =>
  api(`/api/studio/artifacts?limit=${limit}`);
export const getArtifactRequest = (artifactId) =>
  api(`/api/studio/artifacts/${artifactId}`);

// ── Synthesis ─────────────────────────────────────────────────────────────────
export const runSynthesisRequest = (payload) =>
  api("/api/synthesis/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload)
  });
export const detectContradictionsRequest = (sourceIds = []) => {
  const params = new URLSearchParams();
  sourceIds.forEach((id) => params.append("source_ids", id));
  return api(`/api/synthesis/contradictions${params.toString() ? `?${params.toString()}` : ""}`);
};

// ── Exports ──────────────────────────────────────────────────────────────────
export const exportArtifactRequest = (artifactId, format = "markdown") =>
  api(`/api/exports/artifact/${artifactId}?export_format=${format}`, { method: "POST" });
export const downloadArtifactUrl = (artifactId, format = "markdown") =>
  `/api/exports/artifact/${artifactId}/download?export_format=${format}`;
export const exportNotesRequest = (docId = null, format = "markdown") => {
  const params = new URLSearchParams({ export_format: format });
  if (docId) params.set("doc_id", docId);
  return api(`/api/exports/notes?${params.toString()}`, { method: "POST" });
};

// ── Evidence ─────────────────────────────────────────────────────────────────
export const fetchEvidenceRequest = (query = "") =>
  api(`/api/evidence${query ? `?${query}` : ""}`);
export const fetchEvidenceForConceptRequest = (conceptId) =>
  api(`/api/evidence/concept/${conceptId}`);
export const fetchEvidenceForSourceRequest = (sourceId) =>
  api(`/api/evidence/source/${sourceId}`);
