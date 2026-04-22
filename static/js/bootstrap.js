import {
  state,
  defaultNoteTitle,
  ensureCompareSelections,
  getConceptById,
  setPreviewFromCitation,
  setPreviewFromDocument,
  switchSurface,
  syncGraphFiltersWithSelection
} from "./state.js";
import {
  fetchBootstrap,
  fetchConceptExplanation,
  fetchConceptGraph,
  fetchDocument,
  fetchNotes,
  fetchWorkspace,
  fetchWorkspaceV2,
  fetchReviewQueueRequest,
  startDialogueSession,
  sendDialogueMessage
} from "./api.js";

export async function loadWorkspaceState() {
  state.workspace = await fetchWorkspace();
  ensureCompareSelections();
  await loadUnifiedWorkspace();
}

export async function loadUnifiedWorkspace(surface = state.activeSurface) {
  const params = new URLSearchParams();
  if (state.selectedDocumentId) {
    params.append("source_ids", state.selectedDocumentId);
  }
  if (state.selectedConceptId) {
    params.append("concept_ids", state.selectedConceptId);
  }
  if (state.activeSession?.id) {
    params.set("session_id", state.activeSession.id);
  }
  params.set("surface", surface);
  state.workspaceV2 = await fetchWorkspaceV2(params.toString());
  const activeSession = state.workspaceV2.left_rail?.sessions?.find((session) => session.status === "active");
  state.activeSession = activeSession || null;
  state.reviewQueue = await loadReviewQueue();
}

export async function loadReviewQueue() {
  const params = new URLSearchParams();
  if (state.selectedDocumentId) {
    params.append("source_ids", state.selectedDocumentId);
  }
  if (state.activeSession?.id) {
    params.set("session_id", state.activeSession.id);
  }
  const payload = await fetchReviewQueueRequest(params.toString());
  state.reviewQueue = payload.items || [];
  return state.reviewQueue;
}

export async function loadGraph() {
  const params = new URLSearchParams();
  if (state.graphFilters.docId) {
    params.set("doc_id", state.graphFilters.docId);
  } else if (state.graphFilters.subjectName) {
    params.set("subject_name", state.graphFilters.subjectName);
  }
  const suffix = params.toString() ? `?${params.toString()}` : "";
  state.graph = await fetchConceptGraph(suffix);
  if (!state.selectedConceptId || !state.graph.nodes.some((node) => node.id === state.selectedConceptId)) {
    state.selectedConceptId = state.graph.nodes[0]?.id || null;
  }
}

export async function loadCurrentNote() {
  const params = new URLSearchParams({ limit: "1" });
  if (state.selectedDocumentId) {
    params.set("doc_id", state.selectedDocumentId);
  }
  if (state.selectedConceptId) {
    params.set("concept_id", state.selectedConceptId);
  }
  const payload = await fetchNotes(params.toString());
  const note = payload.notes?.[0];
  state.noteTransforms = { flashcards: [], quiz: [] };
  if (note) {
    state.noteDraft = {
      noteId: note.id,
      title: note.title || defaultNoteTitle(),
      content: note.content || "",
      sourceSnippet: note.source_snippet || ""
    };
  } else {
    state.noteDraft = {
      noteId: null,
      title: defaultNoteTitle(),
      content: "",
      sourceSnippet: state.selectedText || ""
    };
  }
}

export async function loadDocumentDetail(docId, options = {}) {
  const { preserveGraphScope = false } = options;
  if (!docId) {
    state.selectedDocumentId = null;
    state.documentDetail = null;
    setPreviewFromDocument();
    return;
  }

  const detail = await fetchDocument(docId);
  state.selectedDocumentId = docId;
  state.documentDetail = detail;
  const nextSubject = detail.document.subject_name || "";

  if (!preserveGraphScope) {
    state.graphFilters.subjectName = nextSubject;
    if (state.graphFilters.docId && state.graphFilters.docId !== detail.document.id) {
      const docStillVisible = state.documents.some(
        (item) => item.id === state.graphFilters.docId && item.subject_name === nextSubject
      );
      if (!docStillVisible) {
        state.graphFilters.docId = "";
      }
    }
  }

  const conceptOptions = detail.concept_options?.length ? detail.concept_options : detail.concepts;
  if (conceptOptions.length) {
    const currentConceptStillVisible = conceptOptions.some((concept) => concept.id === state.selectedConceptId);
    if (!currentConceptStillVisible) {
      state.selectedConceptId = conceptOptions[0].id;
    }
  } else if (!state.graph.nodes.some((concept) => concept.id === state.selectedConceptId)) {
    state.selectedConceptId = state.graph.nodes[0]?.id || null;
  }

  ensureCompareSelections();
  setPreviewFromDocument();
  await loadGraph();
  if (state.selectedConceptId) {
    await loadExplanation();
  }
  await loadCurrentNote();
}

export async function loadExplanation() {
  if (!state.selectedConceptId) {
    state.explanation = null;
    return;
  }
  const level = Number(document.getElementById("depthSlider")?.value || 2);
  state.explanation = await fetchConceptExplanation(state.selectedConceptId, level);
}

export async function startDialogue() {
  const payload = await startDialogueSession(state.selectedConceptId);
  state.sessionId = payload.session_id;
  state.chat = [{ role: "assistant", text: payload.opening_prompt }];
}

export async function sendDialogue(message) {
  const payload = await sendDialogueMessage(state.sessionId, state.selectedConceptId, message);
  state.sessionId = payload.session_id;
  state.chat.push({ role: "assistant", text: payload.reply });
}

export async function loadBootstrapData(options = {}) {
  const { preserveTutor = true } = options;
  const payload = await fetchBootstrap();
  state.documents = payload.documents || [];
  state.questions = payload.questions || [];
  state.dueCards = payload.dueCards || [];
  state.graph = payload.graph || { nodes: [], edges: [] };
  state.stats = payload.stats || state.stats;
  state.workspace = payload.workspace || state.workspace;
  state.currentCardIndex = 0;
  state.showAnswer = false;
  syncGraphFiltersWithSelection();

  if (state.documents.length) {
    const hasSelectedDocument = state.documents.some((docItem) => docItem.id === state.selectedDocumentId);
    if (!hasSelectedDocument) {
      state.selectedDocumentId = state.documents[0].id;
    }
    await loadDocumentDetail(state.selectedDocumentId);
  } else {
    state.selectedDocumentId = null;
    state.documentDetail = null;
    setPreviewFromDocument();
    state.noteDraft = {
      noteId: null,
      title: "Study note",
      content: "",
      sourceSnippet: ""
    };
  }

  if (!state.selectedConceptId && state.graph.nodes.length) {
    state.selectedConceptId = state.graph.nodes[0].id;
  } else if (state.selectedConceptId && !state.graph.nodes.some((concept) => concept.id === state.selectedConceptId)) {
    state.selectedConceptId = state.graph.nodes[0]?.id || null;
  }

  if (state.selectedConceptId) {
    await loadExplanation();
  }

  ensureCompareSelections();
  await loadGraph();
  await loadUnifiedWorkspace();

  if (!preserveTutor) {
    state.tutorMessages = [];
    state.latestTutorResponse = null;
    state.lastTutorQuery = null;
  }

  if (!state.chat.length) {
    await startDialogue();
  }
}

export async function refreshSummaryData() {
  await loadBootstrapData({ preserveTutor: true });
}

export function setPreviewFromFirstCitation(citations) {
  if (citations?.length) {
    setPreviewFromCitation(citations[0]);
  }
}

export function activeConceptName() {
  return getConceptById(state.selectedConceptId)?.name || "this concept";
}
