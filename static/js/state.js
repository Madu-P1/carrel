export function buildDefaultMomentum() {
  return {
    headline: "Upload a source to start building momentum",
    reason: "The engine will prioritize the highest-leverage next step once it can see your concepts and study history.",
    actions: [{ label: "Upload a source", type: "upload" }],
    signals: [],
    momentum_score: 0,
    focus_concept_id: null,
    focus_concept_name: null
  };
}

export const state = {
  documents: [],
  selectedDocumentId: null,
  documentDetail: null,
  questions: [],
  dueCards: [],
  graph: { nodes: [], edges: [] },
  stats: {
    documents: 0,
    questions: 0,
    due: 0,
    retention: 0,
    mastered: 0,
    weakestConcept: "-"
  },
  workspace: {
    goal: "",
    momentum: buildDefaultMomentum(),
    timeline: [],
    mastery: [],
    notes: [],
    compareOptions: [],
    subjects: []
  },
  workspaceV2: {
    scope: {
      source_ids: [],
      concept_ids: [],
      surface: "tutor",
      session_id: null
    },
    left_rail: {
      sources: [],
      goals: [],
      notes: [],
      sessions: [],
      artifacts: [],
      filters: {}
    },
    center_canvas: {
      surface: "tutor",
      payload: {}
    },
    right_rail: {
      evidence: [],
      confidence: {},
      contradictions: [],
      related_concepts: [],
      next_actions: []
    }
  },
  currentCardIndex: 0,
  showAnswer: false,
  selectedConceptId: null,
  explanation: null,
  chat: [],
  sessionId: null,
  workspaceView: "tutor",
  tutorMessages: [],
  latestTutorResponse: null,
  latestEvaluation: null,
  lastTutorQuery: null,
  confidence: 62,
  selectedText: "",
  selectedPreview: null,
  focusMode: false,
  noteDraft: {
    noteId: null,
    title: "",
    content: "",
    sourceSnippet: ""
  },
  noteTransforms: {
    flashcards: [],
    quiz: []
  },
  compare: null,
  activeSession: null,
  sessionSummary: null,
  reviewQueue: [],
  compareLeftId: null,
  compareRightId: null,
  graphFilters: {
    subjectName: "",
    docId: ""
  },
  commandPaletteOpen: false,
  commandQuery: "",
  activeSurface: "tutor",
  sourceRailCollapsed: false,
  evidenceRailCollapsed: false,
  evidenceRailItems: [],
  studioConfig: {
    artifact_kind: "study_guide",
    audience: "student",
    depth: "standard",
    output_length: "medium",
    custom_prompt: ""
  },
  studioArtifact: null,
  synthesisResult: null
};

export function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

export function truncate(text, maxLength = 160) {
  const value = String(text ?? "").trim();
  if (value.length <= maxLength) {
    return value;
  }
  return `${value.slice(0, maxLength - 1)}...`;
}

export function formatDocumentMeta(document) {
  const type = (document.file_type || "file").toUpperCase();
  const pageInfo = document.page_count ? `${document.page_count} pages` : "text document";
  const subject = document.subject_name ? ` · ${document.subject_name}` : "";
  return `${type}${subject} · ${document.status} · ${pageInfo}`;
}

export function shortFileLabel(filename) {
  const value = String(filename || "Source");
  return value.length > 22 ? `${value.slice(0, 21)}...` : value;
}

export function selectedConceptOptions() {
  if (state.documentDetail?.concept_options?.length) {
    return state.documentDetail.concept_options;
  }
  if (state.documentDetail?.concepts?.length) {
    return state.documentDetail.concepts;
  }
  return state.graph.nodes.map((node) => ({
    id: node.id,
    name: node.label,
    description: node.description,
    mastery: node.mastery
  }));
}

export function compareConceptOptions() {
  const currentOptions = selectedConceptOptions();
  if (currentOptions.length) {
    return currentOptions;
  }
  if (state.workspace.compareOptions?.length) {
    return state.workspace.compareOptions;
  }
  return [];
}

export function getConceptById(conceptId) {
  if (!conceptId) {
    return null;
  }
  return selectedConceptOptions().find((concept) => concept.id === conceptId)
    || compareConceptOptions().find((concept) => concept.id === conceptId)
    || state.documentDetail?.concepts?.find((concept) => concept.id === conceptId)
    || state.workspace.compareOptions.find((concept) => concept.id === conceptId)
    || null;
}

export function graphDocuments() {
  const subjectName = state.graphFilters.subjectName;
  return subjectName
    ? state.documents.filter((docItem) => docItem.subject_name === subjectName)
    : state.documents;
}

export function syncGraphFiltersWithSelection() {
  const selectedDoc = state.documents.find((docItem) => docItem.id === state.selectedDocumentId);
  if (selectedDoc) {
    if (!state.graphFilters.subjectName || !state.documents.some((docItem) => docItem.subject_name === state.graphFilters.subjectName)) {
      state.graphFilters.subjectName = selectedDoc.subject_name || "";
    }
    if (!state.graphFilters.docId || !state.documents.some((docItem) => docItem.id === state.graphFilters.docId)) {
      state.graphFilters.docId = selectedDoc.id;
    }
  } else if (!state.documents.length) {
    state.graphFilters.subjectName = "";
    state.graphFilters.docId = "";
  }
}

export function defaultNoteTitle() {
  const concept = getConceptById(state.selectedConceptId);
  if (concept?.name) {
    return `${concept.name} note`;
  }
  if (state.documentDetail?.document?.filename) {
    return `${state.documentDetail.document.filename} note`;
  }
  return "Study note";
}

export function eventLabel(eventType) {
  const labels = {
    goal_updated: "Goal updated",
    tutor_query: "Grounded tutor used",
    note_saved: "Note saved",
    note_transformed: "Note converted to study assets",
    compare_opened: "Compare mode opened",
    card_reviewed: "Card reviewed",
    document_uploaded: "Source uploaded",
    document_deleted: "Source removed",
    dialogue_started: "Socratic session started",
    dialogue_message: "Socratic exchange",
    focus_mode_toggled: "Focus mode toggled",
    source_previewed: "Source previewed",
    momentum_action: "Momentum action used",
    review_event_v2: "Workspace review event",
    session_started: "Focus session started",
    session_completed: "Focus session completed"
  };
  return labels[eventType] || eventType.replaceAll("_", " ");
}

/** Switch the active canvas surface in the 3-pane layout. */
export function switchSurface(surfaceId) {
  state.activeSurface = surfaceId;
  state.workspaceView = surfaceId; // keep legacy alias in sync
  document.querySelectorAll(".surface-btn").forEach((button) => {
    button.classList.toggle("active", button.dataset.surface === surfaceId);
  });
  document.querySelectorAll(".canvas-surface").forEach((panel) => {
    panel.classList.toggle("active", panel.id === `${surfaceId}Surface`);
  });
}

/** @deprecated use switchSurface */
export function switchTab() {}

/** @deprecated use switchSurface */
export function openWorkspaceView(view) {
  switchSurface(view);
}

export function ensureCompareSelections() {
  const options = compareConceptOptions();
  if (!options.length) {
    state.compareLeftId = null;
    state.compareRightId = null;
    return;
  }
  const optionIds = new Set(options.map((option) => option.id));
  if (!state.compareLeftId || !optionIds.has(state.compareLeftId)) {
    state.compareLeftId = state.selectedConceptId && optionIds.has(state.selectedConceptId)
      ? state.selectedConceptId
      : options[0].id;
  }
  if (!state.compareRightId || !optionIds.has(state.compareRightId) || state.compareRightId === state.compareLeftId) {
    const fallback = options.find((option) => option.id !== state.compareLeftId);
    state.compareRightId = fallback ? fallback.id : state.compareLeftId;
  }
}

export function setPreviewFromDocument() {
  if (state.documentDetail) {
    state.selectedPreview = {
      type: "document",
      item: state.documentDetail
    };
  } else {
    state.selectedPreview = null;
  }
}

export function setPreviewFromCitation(citation) {
  state.selectedPreview = {
    type: "citation",
    item: citation
  };
}
