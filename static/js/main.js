import {
  state,
  ensureCompareSelections,
  escapeHtml,
  switchSurface,
  setPreviewFromCitation
} from "./state.js";
import {
  compareConceptsRequest,
  completeSessionRequest,
  createSessionRequest,
  createTutorExchangeRequest,
  deleteDocumentRequest,
  detectContradictionsRequest,
  downloadArtifactUrl,
  evaluateTutorExchangeRequest,
  exportArtifactRequest,
  exportNotesRequest,
  fetchEvidenceRequest,
  generateArtifactRequest,
  listArtifactsRequest,
  getArtifactRequest,
  logEventRequest,
  reviewEventRequest,
  reviewCardRequest,
  runSynthesisRequest,
  saveGoalRequest,
  saveNoteRequest,
  transformNoteRequest,
  uploadDocumentRequest
} from "./api.js";
import {
  activeConceptName,
  loadBootstrapData,
  loadCurrentNote,
  loadDocumentDetail,
  loadExplanation,
  loadGraph,
  loadUnifiedWorkspace,
  loadReviewQueue,
  loadWorkspaceState,
  refreshSummaryData,
  sendDialogue,
  setPreviewFromFirstCitation
} from "./bootstrap.js";
import {
  fillNoteFromRecent,
  previewCitationFromResponse,
  renderWorkspace
} from "./views/workspace.js";
import {
  renderConceptMap,
  renderConceptExplanation,
  renderChatLog,
  setConceptCallbacks,
  getSelectedConcept
} from "./views/concepts.js";

// ── Helpers ───────────────────────────────────────────────────────────────────
function setStatus(message) {
  const el = document.getElementById("uploadStatus");
  if (el) el.textContent = message;
}

// Toast notifications
function showToast(message, type = "info", duration = 3600) {
  const container = document.getElementById("toastContainer");
  if (!container || !message) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.setAttribute("role", type === "error" ? "alert" : "status");
  toast.textContent = message;
  container.appendChild(toast);
  // Trigger enter transition
  requestAnimationFrame(() => toast.classList.add("toast-visible"));
  setTimeout(() => {
    toast.classList.remove("toast-visible");
    toast.classList.add("toast-leaving");
    setTimeout(() => toast.remove(), 260);
  }, duration);
}

function toastError(err) {
  const msg = (err && err.message) || String(err || "Something went wrong.");
  showToast(msg, "error", 4800);
  setStatus(msg);
}

function toastSuccess(message) {
  showToast(message, "success");
  setStatus(message);
}

function toastInfo(message) {
  showToast(message, "info");
  setStatus(message);
}

// Stale warnings
async function refreshStaleBanner() {
  try {
    const data = await fetch("/api/stale/warnings").then((r) => r.ok ? r.json() : null);
    const banner = document.getElementById("staleBanner");
    const text = document.getElementById("staleBannerText");
    if (!banner || !text) return;
    if (sessionStorage.getItem("staleBannerDismissed") === "1") {
      banner.classList.add("hidden");
      return;
    }
    const warnings = (data && (data.warnings || data)) || [];
    const count = Array.isArray(warnings) ? warnings.length : (data?.count || 0);
    if (count > 0) {
      text.textContent = `${count} artifact${count === 1 ? "" : "s"} may be out of date — the underlying source has changed.`;
      banner.classList.remove("hidden");
    } else {
      banner.classList.add("hidden");
    }
  } catch (_) { /* silent */ }
}

// Tutor thinking indicator
function setTutorThinking(on) {
  const feed = document.getElementById("tutorFeed");
  if (!feed) return;
  let el = document.getElementById("tutorThinking");
  if (on) {
    if (!el) {
      el = document.createElement("div");
      el.id = "tutorThinking";
      el.className = "tutor-thinking";
      el.innerHTML = '<span class="dot"></span><span class="dot"></span><span class="dot"></span><span class="thinking-label">Tutor is thinking…</span>';
      feed.appendChild(el);
    }
    feed.scrollTop = feed.scrollHeight;
  } else if (el) {
    el.remove();
  }
}

// Copy to clipboard
async function copyArtifactToClipboard() {
  const artifact = state.studioArtifact;
  if (!artifact || !artifact.content) {
    toastInfo("Nothing to copy yet — generate an artifact first.");
    return;
  }
  try {
    await navigator.clipboard.writeText(artifact.content);
    toastSuccess("Artifact copied to clipboard.");
  } catch (err) {
    toastError(err);
  }
}

function currentEvidenceItems() {
  return state.latestTutorResponse?.evidence?.length
    ? state.latestTutorResponse.evidence
    : (state.evidenceRailItems.length ? state.evidenceRailItems : (state.workspaceV2.right_rail?.evidence || []));
}

async function copyTextToClipboard(text, successMessage) {
  if (!text) {
    toastInfo("Nothing to copy yet.");
    return;
  }
  if (!navigator.clipboard?.writeText) {
    toastInfo("Clipboard access is not available in this browser.");
    return;
  }
  try {
    await navigator.clipboard.writeText(text);
    toastSuccess(successMessage);
  } catch (err) {
    toastError(err);
  }
}

async function ensureEvidenceScope(evidence) {
  if (!evidence) {
    return;
  }

  if (evidence.source_id && evidence.source_id !== state.selectedDocumentId) {
    await loadDocumentDetail(evidence.source_id, { preserveGraphScope: true });
  }

  if (evidence.concept_id && evidence.concept_id !== state.selectedConceptId) {
    state.selectedConceptId = evidence.concept_id;
    ensureCompareSelections();
    await loadExplanation();
    await loadCurrentNote();
  }
}

function applyEvidenceToNoteDraft(evidence) {
  const snippet = evidence.anchor_text || evidence.excerpt || evidence.label || "";
  const sourceLabel = evidence.label || evidence.document_name || "Source evidence";
  const titleBase = activeConceptName();
  const contentParts = [
    state.noteDraft.content.trim(),
    `Source: ${sourceLabel}`,
    snippet
  ].filter(Boolean);

  state.selectedText = snippet;
  state.noteDraft.noteId = null;
  state.noteDraft.title = `${titleBase} evidence note`;
  state.noteDraft.sourceSnippet = snippet;
  state.noteDraft.content = contentParts.join("\n\n");
}

async function handleEvidenceAction(actionType, evidenceId) {
  const evidence = currentEvidenceItems().find((item) => item.id === evidenceId);
  if (!evidence) {
    toastInfo("That evidence item is no longer available.");
    return;
  }

  await ensureEvidenceScope(evidence);

  switch (actionType) {
    case "cite":
      await copyTextToClipboard(
        [evidence.label, evidence.anchor_text || evidence.excerpt].filter(Boolean).join("\n"),
        "Citation copied to clipboard."
      );
      break;
    case "note":
      applyEvidenceToNoteDraft(evidence);
      switchSurface("notes");
      renderAll();
      toastInfo("Evidence anchored in Notes.");
      break;
    case "card":
      applyEvidenceToNoteDraft(evidence);
      switchSurface("notes");
      renderWorkspace();
      await transformCurrentNote();
      renderAll();
      toastSuccess("Card drafts created from evidence.");
      break;
    default:
      break;
  }
}

// ── Command palette ───────────────────────────────────────────────────────────
function getCommandActions() {
  const actions = [
    { id: "open-tutor",     label: "Open Tutor",        hint: "Source-grounded Q&A" },
    { id: "open-concept",   label: "Open Concepts",     hint: "Concept map and mastery" },
    { id: "open-review",    label: "Open Review",       hint: "Spaced repetition" },
    { id: "open-session",   label: "Open Session",      hint: "Focus sprint engine" },
    { id: "open-notes",     label: "Open Notes",        hint: "Capture and transform notes" },
    { id: "open-compare",   label: "Open Compare",      hint: "Contrast two concepts" },
    { id: "open-studio",    label: "Open Studio",       hint: "Generate study artifacts" },
    { id: "open-synthesis", label: "Open Synthesis",    hint: "Cross-source reasoning" },
    { id: "open-upload",    label: "Upload a Source",   hint: "Ingest another document" },
    { id: "toggle-focus",   label: state.focusMode ? "Exit Focus Mode" : "Enter Focus Mode", hint: "Reduce visual load" }
  ];
  const primary = state.workspace.momentum?.actions?.[0];
  if (primary) {
    actions.unshift({ id: "momentum-primary", label: primary.label, hint: state.workspace.momentum.headline });
  }
  return actions;
}

function renderCommandPalette() {
  const palette = document.getElementById("commandPalette");
  palette.classList.toggle("hidden", !state.commandPaletteOpen);
  palette.setAttribute("aria-hidden", state.commandPaletteOpen ? "false" : "true");

  const query = state.commandQuery.trim().toLowerCase();
  const actions = getCommandActions().filter((a) => !query || `${a.label} ${a.hint}`.toLowerCase().includes(query));
  document.getElementById("commandResults").innerHTML = actions.length
    ? actions.map((a) => `
        <button class="command-item" type="button" data-command-id="${escapeHtml(a.id)}">
          <strong>${escapeHtml(a.label)}</strong>
          <small>${escapeHtml(a.hint)}</small>
        </button>`).join("")
    : `<p class="empty-state">No matching actions.</p>`;
}

function openCommandPalette() {
  state.commandPaletteOpen = true;
  renderCommandPalette();
  const input = document.getElementById("commandInput");
  input.value = state.commandQuery;
  input.focus();
}

function closeCommandPalette() {
  state.commandPaletteOpen = false;
  state.commandQuery = "";
  renderCommandPalette();
}

async function runCommand(commandId) {
  closeCommandPalette();
  switch (commandId) {
    case "momentum-primary":
      await handleMomentumAction(state.workspace.momentum?.actions?.[0]);
      return;
    case "open-upload":
      openUploadOverlay();
      return;
    case "toggle-focus":
      state.focusMode = !state.focusMode;
      await logEvent("focus_mode_toggled", { payload: { focus_mode: state.focusMode } });
      renderAll();
      return;
    default:
      if (commandId.startsWith("open-")) {
        switchSurface(commandId.replace("open-", ""));
        await loadUnifiedWorkspace(state.activeSurface);
        renderAll();
      }
  }
}

// ── Upload overlay ────────────────────────────────────────────────────────────
function openUploadOverlay() {
  document.getElementById("uploadOverlay").classList.remove("hidden");
}

function closeUploadOverlay() {
  document.getElementById("uploadOverlay").classList.add("hidden");
}

// ── Logging ───────────────────────────────────────────────────────────────────
async function logEvent(eventType, options = {}) {
  try {
    await logEventRequest({
      event_type: eventType,
      doc_id: options.docId ?? state.selectedDocumentId,
      concept_id: options.conceptId ?? state.selectedConceptId,
      confidence: options.confidence ?? null,
      duration_seconds: options.durationSeconds ?? null,
      payload: options.payload ?? {}
    });
  } catch (_err) {
    // best-effort
  }
}

// ── Evidence rail auto-population ─────────────────────────────────────────────
async function refreshEvidenceRail() {
  try {
    const params = new URLSearchParams();
    if (state.selectedConceptId) params.set("concept_id", state.selectedConceptId);
    else if (state.selectedDocumentId) params.set("source_id", state.selectedDocumentId);
    const result = await fetchEvidenceRequest(params.toString());
    state.evidenceRailItems = result?.evidence || [];
    state.workspaceV2.right_rail = state.workspaceV2.right_rail || {};
    state.workspaceV2.right_rail.evidence = state.evidenceRailItems;
  } catch (_err) {
    // best-effort — evidence rail will show tutor evidence fallback
  }
}

// ── Core renders ──────────────────────────────────────────────────────────────
function renderAll() {
  renderWorkspace();
  renderConceptMap({
    onSelect: async (concept) => {
      try {
        state.selectedConceptId = concept.id;
        await loadExplanation();
        await loadCurrentNote();
        ensureCompareSelections();
        await loadUnifiedWorkspace(state.activeSurface);
        await refreshEvidenceRail();
        renderAll();
      } catch (err) { toastError(err); }
    },
    onTeach: async (concept) => {
      try {
        await openTutorFromConcept(concept);
      } catch (err) { toastError(err); }
    },
    onReview: async (concept) => {
      try {
        state.selectedConceptId = concept.id;
        await loadReviewQueue();
        await loadUnifiedWorkspace("review");
        switchSurface("review");
        renderAll();
      } catch (err) { toastError(err); }
    },
    onCompare: async (concept) => {
      try {
        state.compareLeftId = concept.id;
        ensureCompareSelections();
        switchSurface("compare");
        await loadUnifiedWorkspace("compare");
        renderAll();
      } catch (err) { toastError(err); }
    }
  });
  renderConceptExplanation();
  renderChatLog();
  renderCommandPalette();
}

// ── Tutor ─────────────────────────────────────────────────────────────────────
async function askTutor(question, mode = "standard", selectedText = state.selectedText) {
  const clean = question.trim();
  if (!clean) return;
  const confidence = Number(document.getElementById("confidenceSlider")?.value || state.confidence);
  state.confidence = confidence;
  state.lastTutorQuery = { question: clean, responseMode: mode, selectedText };
  state.tutorMessages.push({ role: "user", text: clean, confidence });
  renderWorkspace();
  setTutorThinking(true);

  let response;
  try {
    response = await createTutorExchangeRequest({
      question: clean,
      session_id: state.activeSession?.id || null,
      source_scope: state.selectedDocumentId ? [state.selectedDocumentId] : [],
      concept_scope: state.selectedConceptId ? [state.selectedConceptId] : [],
      selected_text: selectedText || null,
      learner_confidence: confidence,
      mode: "tutor",
      response_mode: mode,
      depth: "standard",
      evidence_strictness: "citation-heavy"
    });
  } catch (err) {
    setTutorThinking(false);
    toastError(err);
    return;
  }
  setTutorThinking(false);

  state.latestTutorResponse = response;
  state.tutorMessages.push({
    role: "assistant",
    text: response.answer,
    citations: response.citations || [],
    evidence: response.evidence || [],
    exchangeId: response.exchange_id,
    misconceptions: response.misconceptions || [],
    scaffolds: response.scaffolds || [],
    actions: response.actions || []
  });
  previewCitationFromResponse(response);
  await loadUnifiedWorkspace("tutor");
  await loadWorkspaceState();
  renderAll();
}

async function rerunTutor(mode) {
  if (!state.lastTutorQuery) return;
  await askTutor(state.lastTutorQuery.question, mode, state.lastTutorQuery.selectedText);
}

async function openTutorFromConcept(concept) {
  state.selectedConceptId = concept.id;
  await loadExplanation();
  await loadCurrentNote();
  ensureCompareSelections();
  switchSurface("tutor");
  await loadUnifiedWorkspace("tutor");
  await refreshEvidenceRail();
  renderAll();
  setTimeout(() => {
    const input = document.getElementById("tutorInput");
    if (input) {
      input.value = `Teach me ${concept.label} using the source evidence.`;
      input.focus();
    }
  }, 50);
}

async function evaluateLatestTutorExchange() {
  const exchangeId = state.latestTutorResponse?.exchange_id || state.latestTutorResponse?.exchangeId;
  const learnerResponse = document.getElementById("selfCheckInput")?.value.trim();
  if (!exchangeId || !learnerResponse) return;
  state.latestEvaluation = await evaluateTutorExchangeRequest(exchangeId, {
    learner_response: learnerResponse,
    mode: "examiner"
  });
  const suggested = state.latestEvaluation?.repair_path?.surface;
  if (suggested && ["concept", "review", "tutor"].includes(suggested)) {
    switchSurface(suggested);
  }
  await loadUnifiedWorkspace(state.activeSurface);
  renderWorkspace();
}

// ── Goal ──────────────────────────────────────────────────────────────────────
async function saveGoal() {
  const goal = document.getElementById("goalInput")?.value.trim();
  state.workspace = await saveGoalRequest(goal);
  await loadUnifiedWorkspace(state.activeSurface);
  renderWorkspace();
}

// ── Notes ─────────────────────────────────────────────────────────────────────
async function saveNote() {
  const goalId = state.workspaceV2.left_rail?.goals?.[0]?.id;
  const noteType = document.getElementById("noteTypeSelect")?.value || "citation_backed_claim";
  const response = await saveNoteRequest({
    note_id: state.noteDraft.noteId,
    doc_id: state.selectedDocumentId,
    concept_id: state.selectedConceptId,
    title: state.noteDraft.title,
    content: state.noteDraft.content,
    source_snippet: state.noteDraft.sourceSnippet || state.selectedText || null,
    note_type: noteType,
    goal_id: goalId && goalId !== "legacy-goal" ? goalId : null,
    session_id: state.activeSession?.id || null,
    evidence_reference_ids: (state.latestTutorResponse?.evidence || []).map((e) => e.id)
  });
  state.noteDraft.noteId = response.note.id;
  state.noteDraft.title = response.note.title;
  state.noteDraft.content = response.note.content;
  state.noteDraft.sourceSnippet = response.note.source_snippet || "";
  state.workspace = response.workspace;
  await loadUnifiedWorkspace("notes");
  renderWorkspace();
}

async function transformCurrentNote() {
  state.noteTransforms = await transformNoteRequest({
    content: state.noteDraft.content,
    doc_id: state.selectedDocumentId,
    concept_id: state.selectedConceptId
  });
  await loadWorkspaceState();
  renderWorkspace();
}

function applySelectedTextToNote() {
  if (!state.selectedText) return;
  state.noteDraft.sourceSnippet = state.selectedText;
  state.noteDraft.content = `${state.noteDraft.content.trim()}\n\nSource anchor: ${state.selectedText}`.trim();
  switchSurface("notes");
  renderWorkspace();
}

function captureSelectedText() {
  const selection = window.getSelection();
  const value = selection ? selection.toString().trim() : "";
  if (!value) return;
  state.selectedText = value;
  state.noteDraft.sourceSnippet = value;
  renderWorkspace();
}

// ── Compare ───────────────────────────────────────────────────────────────────
async function runCompare() {
  if (!state.compareLeftId || !state.compareRightId) return;
  if (state.compareLeftId === state.compareRightId) {
    throw new Error("Choose two different concepts.");
  }
  state.compare = await compareConceptsRequest(state.compareLeftId, state.compareRightId);
  setPreviewFromFirstCitation(state.compare.citations);
  await loadWorkspaceState();
  await loadUnifiedWorkspace("compare");
  renderAll();
}

// ── Review ────────────────────────────────────────────────────────────────────
async function submitWorkspaceReview(outcome) {
  const current = state.reviewQueue[0];
  if (!current) return;
  const result = await reviewEventRequest({
    item_id: current.id,
    item_kind: "flashcard",
    outcome,
    classification: outcome === "missed" ? "omission" : "shallow_but_correct",
    confidence: state.confidence,
    duration_seconds: 20,
    session_id: state.activeSession?.id || null
  });
  state._reviewDone = (state._reviewDone || 0) + 1;
  state.reviewQueue.shift();
  state.sessionSummary = { ...state.sessionSummary, lastReviewResult: result };
  await loadReviewQueue();
  await loadUnifiedWorkspace("review");
  renderWorkspace();
}

async function submitSrsReview(rating) {
  const current = state.dueCards[state.currentCardIndex];
  if (!current) return;
  await reviewCardRequest(current.id, rating);
  state.dueCards.splice(state.currentCardIndex, 1);
  if (state.currentCardIndex >= state.dueCards.length) {
    state.currentCardIndex = Math.max(state.dueCards.length - 1, 0);
  }
  state.showAnswer = false;
  await refreshSummaryData();
  renderAll();
}

// ── Session ───────────────────────────────────────────────────────────────────
async function startWorkspaceSession() {
  const objective = document.getElementById("sessionObjective")?.value.trim()
    || `Strengthen ${activeConceptName()} with evidence-backed practice`;
  const duration = Number(document.getElementById("sessionDuration")?.value || 25);
  const mode = document.getElementById("sessionMode")?.value || "focus_sprint";
  const difficulty = document.getElementById("sessionDifficulty")?.value || "standard";
  const goalId = state.workspaceV2.left_rail?.goals?.[0]?.id;

  state.activeSession = await createSessionRequest({
    goal_id: goalId && goalId !== "legacy-goal" ? goalId : null,
    source_scope: state.selectedDocumentId ? [state.selectedDocumentId] : [],
    concept_scope: state.selectedConceptId ? [state.selectedConceptId] : [],
    mode,
    difficulty_target: difficulty,
    duration_minutes: duration,
    objective
  });
  await loadUnifiedWorkspace("session");
  renderWorkspace();
}

async function completeWorkspaceSession() {
  if (!state.activeSession?.id) return;
  state.sessionSummary = await completeSessionRequest(state.activeSession.id);
  state.activeSession = null;
  await loadUnifiedWorkspace("session");
  renderWorkspace();
}

// ── Studio ────────────────────────────────────────────────────────────────────
async function generateArtifact() {
  const kind = document.getElementById("artifactKindSelect")?.value || "study_guide";
  const audience = document.getElementById("artifactAudience")?.value || "student";
  const depth = document.getElementById("artifactDepth")?.value || "standard";
  const outputLength = document.getElementById("artifactLength")?.value || "medium";
  const customPrompt = document.getElementById("artifactCustomPrompt")?.value || "";

  state.studioConfig = { artifact_kind: kind, audience, depth, output_length: outputLength, custom_prompt: customPrompt };
  state.studioArtifact = null;
  renderWorkspace();

  const payload = await generateArtifactRequest({
    artifact_kind: kind,
    source_ids: state.selectedDocumentId ? [state.selectedDocumentId] : [],
    concept_ids: state.selectedConceptId ? [state.selectedConceptId] : [],
    goal_id: state.workspaceV2.left_rail?.goals?.[0]?.id || null,
    session_id: state.activeSession?.id || null,
    audience,
    difficulty: depth,
    depth,
    style: "clear",
    output_length: outputLength,
    evidence_strictness: "relaxed",
    custom_prompt: customPrompt || null
  });

  state.studioArtifact = payload;
  await loadUnifiedWorkspace("studio");
  renderWorkspace();
}

async function loadArtifact(artifactId) {
  const artifact = await getArtifactRequest(artifactId);
  state.studioArtifact = artifact;
  switchSurface("studio");
  renderWorkspace();
}

// ── Exports ──────────────────────────────────────────────────────────────────
async function exportCurrentArtifact(format) {
  const artifactId = state.studioArtifact?.id;
  if (!artifactId) { toastInfo("Generate an artifact first."); return; }
  try {
    // Trigger a download via a hidden link
    const url = downloadArtifactUrl(artifactId, format);
    const link = document.createElement("a");
    link.href = url;
    link.download = "";
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    toastSuccess(`Exported artifact as ${format}.`);
  } catch (err) { toastError(err); }
}

async function exportAllNotes() {
  try {
    const result = await exportNotesRequest(state.selectedDocumentId, "markdown");
    if (result.error) { toastError(new Error(result.error)); return; }
    toastSuccess(`Exported ${result.note_count} notes to ${result.filename}`);
  } catch (err) { toastError(err); }
}

// ── Synthesis ─────────────────────────────────────────────────────────────────
async function runSynthesis() {
  const synthesisType = document.getElementById("synthesisType")?.value || "compare";
  const sourceIds = state.selectedDocumentId ? [state.selectedDocumentId] : [];
  state.synthesisResult = await runSynthesisRequest({ source_ids: sourceIds, synthesis_type: synthesisType });
  await loadUnifiedWorkspace("synthesis");
  renderWorkspace();
}

async function detectContradictions() {
  const sourceIds = state.selectedDocumentId ? [state.selectedDocumentId] : [];
  const result = await detectContradictionsRequest(sourceIds);
  state.synthesisResult = { ...state.synthesisResult, contradictions: result.contradictions || [] };
  renderWorkspace();
}

// ── Document management ───────────────────────────────────────────────────────
async function uploadDocument(file) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  const subject = document.getElementById("uploadSubjectInput")?.value.trim() || "General";
  formData.append("subject_name", subject);
  toastInfo(`Uploading ${file.name}…`);
  const result = await uploadDocumentRequest(formData);
  toastSuccess(`${file.name} processed under ${subject}.`);
  state.selectedDocumentId = result.doc_id;
  await refreshSummaryData();
  await loadUnifiedWorkspace("tutor");
  await refreshEvidenceRail();
  closeUploadOverlay();
  renderAll();
}

async function deleteSelectedDocument() {
  if (!state.selectedDocumentId || !state.documentDetail) return;
  const filename = state.documentDetail.document.filename;
  if (!window.confirm(`Remove "${filename}" from Einstein Tutor?`)) return;
  await deleteDocumentRequest(state.selectedDocumentId);
  state.selectedDocumentId = null;
  state.documentDetail = null;
  state.selectedPreview = null;
  toastSuccess(`${filename} removed.`);
  await refreshSummaryData();
  await loadUnifiedWorkspace(state.activeSurface);
  renderAll();
}

// ── Momentum ──────────────────────────────────────────────────────────────────
async function handleMomentumAction(action) {
  if (!action) { openUploadOverlay(); return; }
  if (action.concept_id) {
    state.selectedConceptId = action.concept_id;
    await loadExplanation();
    await loadCurrentNote();
    ensureCompareSelections();
  }
  switch (action.type) {
    case "upload":   openUploadOverlay(); break;
    case "focus":    state.focusMode = true; switchSurface("session"); break;
    case "tutor":
      switchSurface("tutor");
      setTimeout(() => {
        const input = document.getElementById("tutorInput");
        if (input) input.value = `Help me understand ${activeConceptName()} using the source evidence.`;
      }, 50);
      break;
    case "review":   switchSurface("review"); break;
    case "note":     switchSurface("notes"); break;
    case "compare":
      state.compareLeftId = action.concept_id || state.compareLeftId;
      state.compareRightId = action.related_concept_id || state.compareRightId;
      switchSurface("compare");
      if (state.compareRightId && state.compareRightId !== state.compareLeftId) {
        await runCompare();
        return;
      }
      break;
    default: break;
  }
  await loadUnifiedWorkspace(state.activeSurface);
  await logEvent("momentum_action", { conceptId: action.concept_id, payload: { action_type: action.type } });
  renderAll();
}

// ── Rail collapse ─────────────────────────────────────────────────────────────
function toggleSourceRail() {
  state.sourceRailCollapsed = !state.sourceRailCollapsed;
  const rail = document.getElementById("sourceRail");
  rail.classList.toggle("collapsed", state.sourceRailCollapsed);
  const btn = document.getElementById("sourceRailToggle");
  if (btn) btn.textContent = state.sourceRailCollapsed ? "›" : "‹";
}

function toggleEvidenceRail() {
  state.evidenceRailCollapsed = !state.evidenceRailCollapsed;
  const rail = document.getElementById("evidenceRail");
  rail.classList.toggle("collapsed", state.evidenceRailCollapsed);
  const btn = document.getElementById("evidenceRailToggle");
  if (btn) btn.textContent = state.evidenceRailCollapsed ? "‹" : "›";
}

// ── Event binding ─────────────────────────────────────────────────────────────
function bindEvents() {
  // Surface navigation
  document.querySelectorAll(".surface-btn").forEach((btn) => {
    btn.addEventListener("click", async () => {
      switchSurface(btn.dataset.surface);
      await loadUnifiedWorkspace(btn.dataset.surface);
      await refreshEvidenceRail();
      renderAll();
    });
  });

  // Rail toggles
  document.getElementById("sourceRailToggle").addEventListener("click", toggleSourceRail);
  document.getElementById("evidenceRailToggle").addEventListener("click", toggleEvidenceRail);

  // Header scope selects
  document.getElementById("headerDocSelect").addEventListener("change", async (ev) => {
    try {
      await loadDocumentDetail(ev.target.value);
      await loadUnifiedWorkspace(state.activeSurface);
      refreshEvidenceRail().then(() => renderAll());
      renderAll();
    } catch (err) { toastError(err); }
  });
  document.getElementById("headerConceptSelect").addEventListener("change", async (ev) => {
    state.selectedConceptId = ev.target.value || null;
    ensureCompareSelections();
    await loadExplanation();
    await loadCurrentNote();
    await loadUnifiedWorkspace(state.activeSurface);
    refreshEvidenceRail().then(() => renderAll());
    renderAll();
  });

  // Confidence slider
  document.getElementById("confidenceSlider").addEventListener("input", (ev) => {
    state.confidence = Number(ev.target.value);
    document.getElementById("confidenceValue").textContent = `${state.confidence}%`;
  });

  // Momentum action button (header)
  document.getElementById("momentumActionBtn").addEventListener("click", async () => {
    await handleMomentumAction(state.workspace.momentum?.actions?.[0]);
  });

  // Momentum actions (right rail)
  document.getElementById("momentumActions").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-momentum-index]");
    if (btn) {
      const action = state.workspace.momentum?.actions?.[Number(btn.dataset.momentumIndex)];
      await handleMomentumAction(action);
    }
  });

  // Next actions rail
  document.getElementById("nextActionsList").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-action-type]");
    if (!btn) return;
    const type = btn.dataset.actionType;
    const conceptId = btn.dataset.actionConcept;
    if (conceptId) state.selectedConceptId = conceptId;
    if (type && ["tutor", "review", "notes", "compare", "concept"].includes(type)) {
      switchSurface(type === "notes" ? "notes" : type);
      await loadUnifiedWorkspace(state.activeSurface);
      renderAll();
    }
  });

  document.getElementById("evidenceList").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-ev-action][data-ev-id]");
    if (!btn) {
      return;
    }
    try {
      await handleEvidenceAction(btn.dataset.evAction, btn.dataset.evId);
    } catch (err) {
      toastError(err);
    }
  });

  // Upload overlay
  document.getElementById("uploadTriggerBtn").addEventListener("click", openUploadOverlay);
  document.getElementById("uploadCloseBtn").addEventListener("click", closeUploadOverlay);
  document.getElementById("uploadOverlay").addEventListener("click", (ev) => {
    if (ev.target === ev.currentTarget) closeUploadOverlay();
  });

  // File input
  document.getElementById("docInput").addEventListener("change", async (ev) => {
    try {
      await uploadDocument(ev.target.files[0]);
      ev.target.value = "";
    } catch (err) { toastError(err); }
  });

  // Left rail source click
  document.getElementById("railSourceList").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-doc-id]");
    if (!btn) return;
    try {
      await loadDocumentDetail(btn.dataset.docId);
      await loadUnifiedWorkspace(state.activeSurface);
      renderAll();
    } catch (err) { toastError(err); }
  });

  // Left rail note click
  document.getElementById("railNotesList").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-note-id]");
    if (!btn) return;
    const note = state.workspace.notes.find((n) => n.id === btn.dataset.noteId);
    if (note) { fillNoteFromRecent(note); switchSurface("notes"); renderWorkspace(); }
  });

  // Left rail artifact click
  document.getElementById("railArtifactsList").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-artifact-id]");
    if (!btn) return;
    try { await loadArtifact(btn.dataset.artifactId); } catch (err) { toastError(err); }
  });

  // New session from rail
  document.getElementById("railNewSessionBtn").addEventListener("click", () => {
    switchSurface("session");
    renderWorkspace();
  });

  // Focus mode toggle
  document.getElementById("focusModeToggle").addEventListener("click", async () => {
    state.focusMode = !state.focusMode;
    await logEvent("focus_mode_toggled", { payload: { focus_mode: state.focusMode } });
    renderWorkspace();
  });

  // Refresh workspace
  document.getElementById("refreshWorkspaceBtn").addEventListener("click", async () => {
    await loadWorkspaceState();
    await loadUnifiedWorkspace(state.activeSurface);
    await refreshEvidenceRail();
    renderWorkspace();
  });

  // Command palette
  document.getElementById("commandPaletteToggle").addEventListener("click", openCommandPalette);
  document.getElementById("paletteBackdrop").addEventListener("click", closeCommandPalette);
  document.getElementById("commandInput").addEventListener("input", (ev) => {
    state.commandQuery = ev.target.value;
    renderCommandPalette();
  });
  document.getElementById("commandResults").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-command-id]");
    if (btn) await runCommand(btn.dataset.commandId);
  });

  // Goal
  document.getElementById("saveGoalBtn").addEventListener("click", async () => {
    try { await saveGoal(); } catch (err) { toastError(err); }
  });

  // ── TUTOR SURFACE ─────────────────────────────────────────────────────────
  document.getElementById("tutorForm").addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const input = document.getElementById("tutorInput");
    const question = input.value.trim();
    if (!question) return;
    input.value = "";
    try {
      await askTutor(question);
    } catch (err) {
      state.tutorMessages.push({ role: "assistant", text: err.message });
      renderWorkspace();
    }
  });

  document.getElementById("clearTutorBtn").addEventListener("click", () => {
    state.tutorMessages = [];
    state.latestTutorResponse = null;
    state.lastTutorQuery = null;
    renderWorkspace();
  });

  document.getElementById("submitSelfCheckBtn").addEventListener("click", async () => {
    try { await evaluateLatestTutorExchange(); } catch (err) { toastError(err); }
  });

  document.getElementById("askSelectionBtn").addEventListener("click", async () => {
    if (state.selectedText) await askTutor("Explain this selected passage using the source.", "standard", state.selectedText);
  });
  document.getElementById("noteSelectionBtn").addEventListener("click", applySelectedTextToNote);
  document.getElementById("simplifySelectionBtn").addEventListener("click", async () => {
    if (state.selectedText) await askTutor("Explain this in simpler language.", "easier", state.selectedText);
  });

  document.getElementById("tutorFeed").addEventListener("click", async (ev) => {
    const chip = ev.target.closest("[data-message-index][data-citation-index]");
    if (!chip) return;
    const msg = state.tutorMessages[Number(chip.dataset.messageIndex)];
    const cit = msg?.citations?.[Number(chip.dataset.citationIndex)];
    if (!cit) return;
    setPreviewFromCitation(cit);
    await logEvent("source_previewed", { docId: cit.document_id, payload: { source: "tutor_citation" } });
    renderWorkspace();
  });

  // ── CONCEPT SURFACE ───────────────────────────────────────────────────────
  document.getElementById("depthSlider").addEventListener("input", async () => {
    await loadExplanation();
    renderConceptExplanation();
  });

  document.getElementById("graphSubjectSelect").addEventListener("change", async (ev) => {
    state.graphFilters.subjectName = ev.target.value;
    state.graphFilters.docId = "";
    await loadGraph();
    await loadExplanation();
    await refreshEvidenceRail();
    renderAll();
  });

  document.getElementById("graphDocumentSelect").addEventListener("change", async (ev) => {
    state.graphFilters.docId = ev.target.value;
    if (state.graphFilters.docId) {
      const doc = state.documents.find((d) => d.id === state.graphFilters.docId);
      state.graphFilters.subjectName = doc?.subject_name || state.graphFilters.subjectName;
      await loadDocumentDetail(state.graphFilters.docId);
    }
    await loadGraph();
    await loadExplanation();
    await refreshEvidenceRail();
    renderAll();
  });

  document.getElementById("teachConceptBtn").addEventListener("click", async () => {
    const concept = getSelectedConcept();
    if (concept) {
      try { await openTutorFromConcept(concept); } catch (err) { toastError(err); }
    }
  });

  document.getElementById("quizConceptBtn").addEventListener("click", async () => {
    const concept = getSelectedConcept();
    if (concept) {
      state.selectedConceptId = concept.id;
      try {
        await loadReviewQueue();
        switchSurface("review");
        await loadUnifiedWorkspace("review");
        renderAll();
      } catch (err) { toastError(err); }
    }
  });

  document.getElementById("addConceptNoteBtn").addEventListener("click", () => {
    const concept = getSelectedConcept();
    if (concept) {
      state.selectedConceptId = concept.id;
      switchSurface("notes");
      renderWorkspace();
    }
  });

  document.getElementById("compareConceptBtn").addEventListener("click", async () => {
    const concept = getSelectedConcept();
    if (concept) {
      state.compareLeftId = concept.id;
      ensureCompareSelections();
      switchSurface("compare");
      await loadUnifiedWorkspace("compare");
      renderAll();
    }
  });

  // ── REVIEW SURFACE ────────────────────────────────────────────────────────
  document.getElementById("reviewQueue").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-review-outcome]");
    if (!btn) return;
    try { await submitWorkspaceReview(btn.dataset.reviewOutcome); } catch (err) { toastError(err); }
  });

  document.getElementById("rerunMissedBtn").addEventListener("click", async () => {
    await loadReviewQueue();
    renderWorkspace();
  });

  document.getElementById("shuffleReviewBtn").addEventListener("click", () => {
    state.reviewQueue = [...state.reviewQueue].sort(() => Math.random() - 0.5);
    renderWorkspace();
  });

  // ── SESSION SURFACE ───────────────────────────────────────────────────────
  document.getElementById("startSessionBtn").addEventListener("click", async () => {
    try { await startWorkspaceSession(); } catch (err) { toastError(err); }
  });
  document.getElementById("completeSessionBtn").addEventListener("click", async () => {
    try { await completeWorkspaceSession(); } catch (err) { toastError(err); }
  });

  // ── NOTES SURFACE ─────────────────────────────────────────────────────────
  document.getElementById("noteTitleInput").addEventListener("input", (ev) => {
    state.noteDraft.title = ev.target.value;
  });
  document.getElementById("noteEditor").addEventListener("input", (ev) => {
    state.noteDraft.content = ev.target.value;
  });
  document.getElementById("saveNoteBtn").addEventListener("click", async () => {
    try { await saveNote(); } catch (err) { toastError(err); }
  });
  document.getElementById("transformNoteBtn").addEventListener("click", async () => {
    try { await transformCurrentNote(); } catch (err) { toastError(err); }
  });
  document.getElementById("recentNotesList").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-note-id]");
    if (!btn) return;
    const note = state.workspace.notes.find((n) => n.id === btn.dataset.noteId);
    if (note) { fillNoteFromRecent(note); switchSurface("notes"); renderWorkspace(); }
  });
  document.getElementById("noteFilterType").addEventListener("change", () => {
    renderWorkspace();
  });
  document.getElementById("exportNotesBtn").addEventListener("click", async () => {
    try { await exportAllNotes(); } catch (err) { toastError(err); }
  });

  // ── COMPARE SURFACE ───────────────────────────────────────────────────────
  document.getElementById("compareLeftSelect").addEventListener("change", (ev) => {
    state.compareLeftId = ev.target.value;
  });
  document.getElementById("compareRightSelect").addEventListener("change", (ev) => {
    state.compareRightId = ev.target.value;
  });
  document.getElementById("runCompareBtn").addEventListener("click", async () => {
    try { await runCompare(); } catch (err) { toastError(err); }
  });
  document.getElementById("compareCitationList").addEventListener("click", async (ev) => {
    const chip = ev.target.closest("[data-compare-citation-index]");
    if (!chip) return;
    const cit = state.compare?.citations?.[Number(chip.dataset.compareCitationIndex)];
    if (!cit) return;
    setPreviewFromCitation(cit);
    await logEvent("source_previewed", { docId: cit.document_id, payload: { source: "compare_citation" } });
    renderWorkspace();
  });

  // ── STUDIO SURFACE ────────────────────────────────────────────────────────
  document.getElementById("generateArtifactBtn").addEventListener("click", async () => {
    try { await generateArtifact(); } catch (err) { toastError(err); }
  });
  document.getElementById("exportArtifactMdBtn").addEventListener("click", () => exportCurrentArtifact("markdown"));
  document.getElementById("exportArtifactTxtBtn").addEventListener("click", () => exportCurrentArtifact("text"));
  document.getElementById("exportArtifactJsonBtn").addEventListener("click", () => exportCurrentArtifact("json"));
  const copyArtifactBtn = document.getElementById("copyArtifactBtn");
  if (copyArtifactBtn) copyArtifactBtn.addEventListener("click", () => copyArtifactToClipboard());
  document.getElementById("recentArtifactsList").addEventListener("click", async (ev) => {
    const btn = ev.target.closest("[data-load-artifact]");
    if (!btn) return;
    try { await loadArtifact(btn.dataset.loadArtifact); } catch (err) { toastError(err); }
  });

  // ── SYNTHESIS SURFACE ─────────────────────────────────────────────────────
  document.getElementById("runSynthesisBtn").addEventListener("click", async () => {
    try { await runSynthesis(); } catch (err) { toastError(err); }
  });
  document.getElementById("detectContradictionsBtn").addEventListener("click", async () => {
    try { await detectContradictions(); } catch (err) { toastError(err); }
  });

  // ── KEYBOARD SHORTCUTS ────────────────────────────────────────────────────
  window.addEventListener("keydown", async (ev) => {
    if ((ev.metaKey || ev.ctrlKey) && ev.key.toLowerCase() === "k") {
      ev.preventDefault();
      state.commandPaletteOpen ? closeCommandPalette() : openCommandPalette();
      return;
    }
    if (ev.key === "Escape") {
      if (state.commandPaletteOpen) { closeCommandPalette(); return; }
      const overlay = document.getElementById("uploadOverlay");
      if (!overlay.classList.contains("hidden")) { closeUploadOverlay(); return; }
      if (state.selectedText) { state.selectedText = ""; renderWorkspace(); }
    }
  });

  // Text selection (for "Ask / Note / Simplify" bar)
  window.addEventListener("mouseup", captureSelectedText);

  // Stale banner dismiss
  const staleDismiss = document.getElementById("staleBannerDismiss");
  if (staleDismiss) {
    staleDismiss.addEventListener("click", () => {
      sessionStorage.setItem("staleBannerDismissed", "1");
      document.getElementById("staleBanner")?.classList.add("hidden");
    });
  }
}

// ── Init ──────────────────────────────────────────────────────────────────────
async function init() {
  // Ensure tutor surface is active on load
  switchSurface("tutor");
  bindEvents();
  await loadBootstrapData({ preserveTutor: true });
  refreshEvidenceRail().then(() => renderAll());
  refreshStaleBanner();
  renderAll();
}

init().catch((err) => {
  toastError(err);
  console.error(err);
});
