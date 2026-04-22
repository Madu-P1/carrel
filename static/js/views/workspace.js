import {
  buildDefaultMomentum,
  defaultNoteTitle,
  escapeHtml,
  eventLabel,
  formatDocumentMeta,
  getConceptById,
  compareConceptOptions,
  selectedConceptOptions,
  setPreviewFromCitation,
  state,
  truncate
} from "../state.js";

// ── Lightweight Markdown → HTML renderer ─────────────────────────────────────
function renderMarkdown(md) {
  if (!md) return "";
  let html = escapeHtml(md);
  // Code blocks (fenced ```...```)
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (_m, lang, code) =>
    `<pre><code class="lang-${lang}">${code.trim()}</code></pre>`);
  // Inline code
  html = html.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Headings (### → h3, ## → h2, # → h1)
  html = html.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  html = html.replace(/^## (.+)$/gm, "<h2>$1</h2>");
  html = html.replace(/^# (.+)$/gm, "<h1>$1</h1>");
  // Bold and italic
  html = html.replace(/\*\*\*(.+?)\*\*\*/g, "<strong><em>$1</em></strong>");
  html = html.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  html = html.replace(/\*(.+?)\*/g, "<em>$1</em>");
  html = html.replace(/_(.+?)_/g, "<em>$1</em>");
  // Blockquotes
  html = html.replace(/^&gt; (.+)$/gm, "<blockquote>$1</blockquote>");
  // Unordered lists
  html = html.replace(/^- (.+)$/gm, "<li>$1</li>");
  html = html.replace(/((?:<li>.*<\/li>\n?)+)/g, "<ul>$1</ul>");
  // Ordered lists
  html = html.replace(/^\d+\. (.+)$/gm, "<li>$1</li>");
  // Horizontal rules
  html = html.replace(/^---$/gm, "<hr>");
  // Paragraphs (double newlines)
  html = html.replace(/\n\n/g, "</p><p>");
  html = `<p>${html}</p>`;
  // Clean up empty paragraphs
  html = html.replace(/<p>\s*<\/p>/g, "");
  html = html.replace(/<p>\s*(<h[1-3]>)/g, "$1");
  html = html.replace(/(<\/h[1-3]>)\s*<\/p>/g, "$1");
  html = html.replace(/<p>\s*(<pre>)/g, "$1");
  html = html.replace(/(<\/pre>)\s*<\/p>/g, "$1");
  html = html.replace(/<p>\s*(<ul>)/g, "$1");
  html = html.replace(/(<\/ul>)\s*<\/p>/g, "$1");
  html = html.replace(/<p>\s*(<blockquote>)/g, "$1");
  html = html.replace(/(<\/blockquote>)\s*<\/p>/g, "$1");
  html = html.replace(/<p>\s*(<hr>)/g, "$1");
  return html;
}

// ── Header stats ──────────────────────────────────────────────────────────────
export function renderHeaderStats() {
  const el = (id) => document.getElementById(id);
  el("headerDocs").textContent = state.stats.documents;
  el("headerQuestions").textContent = state.stats.questions;
  el("headerDue").textContent = state.stats.due;
  el("headerRetention").textContent = Math.round(state.stats.retention || 0);

  const badge = el("dueCountBadge");
  if (badge) {
    badge.textContent = state.stats.due;
    badge.classList.toggle("hidden", state.stats.due === 0);
  }
}

// ── Scope selects (header) ────────────────────────────────────────────────────
export function renderScopeSelects() {
  const docSelect = document.getElementById("headerDocSelect");
  const conceptSelect = document.getElementById("headerConceptSelect");

  docSelect.innerHTML = state.documents.length
    ? state.documents.map((doc) => `
        <option value="${escapeHtml(doc.id)}" ${doc.id === state.selectedDocumentId ? "selected" : ""}>
          ${escapeHtml(doc.filename)}
        </option>
      `).join("")
    : `<option value="">No sources loaded</option>`;
  docSelect.disabled = !state.documents.length;

  const concepts = selectedConceptOptions();
  conceptSelect.innerHTML = concepts.length
    ? concepts.map((c) => `
        <option value="${escapeHtml(c.id)}" ${c.id === state.selectedConceptId ? "selected" : ""}
          title="${escapeHtml(c.selector_reason || c.description || "")}">
          ${escapeHtml(c.name || c.label)}
        </option>
      `).join("")
    : `<option value="">No concepts yet</option>`;
  conceptSelect.disabled = !concepts.length;

  const caption = state.selectedDocumentId
    ? `${state.documentDetail?.document?.filename || "Source"} · ${getConceptById(state.selectedConceptId)?.name || "All concepts"}`
    : "No source selected.";
  const el = document.getElementById("tutorContextCaption");
  if (el) el.textContent = caption;

  // confidence
  const slider = document.getElementById("confidenceSlider");
  if (slider) slider.value = String(state.confidence);
  const val = document.getElementById("confidenceValue");
  if (val) val.textContent = `${state.confidence}%`;
}

// ── Left rail ─────────────────────────────────────────────────────────────────
export function renderSourceRail() {
  // Sources section
  const sourceList = document.getElementById("railSourceList");
  const sourceCount = document.getElementById("railSourceCount");
  sourceCount.textContent = state.documents.length;
  const citedDocs = new Set((state.latestTutorResponse?.citations || []).map((c) => c.document_id));
  sourceList.innerHTML = state.documents.length
    ? state.documents.map((doc) => `
        <button class="rail-item ${doc.id === state.selectedDocumentId ? "active" : ""} ${citedDocs.has(doc.id) ? "cited" : ""}"
          type="button" data-doc-id="${escapeHtml(doc.id)}">
          <div class="rail-item-head">
            <strong>${escapeHtml(doc.filename)}</strong>
            ${citedDocs.has(doc.id) ? `<span class="source-badge">Cited</span>` : ""}
          </div>
          <span class="detail-meta">${doc.concept_count || 0} concepts · ${doc.status || "ready"}</span>
        </button>
      `).join("")
    : `<p class="empty-state">Upload a source to start.</p>`;

  // Goal
  const goalInput = document.getElementById("goalInput");
  if (goalInput && document.activeElement !== goalInput) {
    goalInput.value = state.workspace.goal || "";
  }

  // Mastery
  const masteryList = document.getElementById("railMasteryList");
  const masterySummary = document.getElementById("railMasterySummary");
  const mastery = state.workspace.mastery || [];
  masterySummary.textContent = mastery.length ? `${mastery.length} tracked` : "";
  masteryList.innerHTML = mastery.length
    ? mastery.map((item) => `
        <div class="mastery-bar-row">
          <div class="mastery-bar-head">
            <strong>${escapeHtml(item.name)}</strong>
            <span>${item.mastery}%</span>
          </div>
          <div class="mini-progress"><span style="width:${item.mastery}%"></span></div>
          <span class="detail-meta">${escapeHtml(item.band)} · ${item.due_cards} due</span>
        </div>
      `).join("")
    : `<p class="empty-state">Mastery tracking begins after concepts are generated.</p>`;

  // Notes count
  const notesCount = document.getElementById("railNotesCount");
  notesCount.textContent = state.workspace.notes?.length || 0;
  const notesList = document.getElementById("railNotesList");
  const notes = state.workspace.notes || [];
  notesList.innerHTML = notes.length
    ? notes.slice(0, 5).map((note) => `
        <button class="rail-item" type="button" data-note-id="${escapeHtml(note.id)}">
          <strong>${escapeHtml(truncate(note.title, 40))}</strong>
          <span class="detail-meta">${escapeHtml(note.note_type || "note").replaceAll("_", " ")}</span>
        </button>
      `).join("")
    : `<p class="empty-state">Notes appear here after saving.</p>`;

  // Sessions
  const sessionsList = document.getElementById("railSessionsList");
  const recentSessions = state.workspaceV2.left_rail?.sessions || [];
  sessionsList.innerHTML = recentSessions.length
    ? recentSessions.map((session) => `
        <div class="rail-item">
          <strong>${escapeHtml(truncate(session.objective || "Focus sprint", 36))}</strong>
          <span class="detail-meta">${escapeHtml(session.status || "")} · ${session.duration_minutes || 25}m</span>
        </div>
      `).join("")
    : `<p class="empty-state">Start a session to track focus time.</p>`;

  // Artifacts
  const artifactsList = document.getElementById("railArtifactsList");
  const artifacts = state.workspaceV2.left_rail?.artifacts || [];
  artifactsList.innerHTML = artifacts.length
    ? artifacts.map((a) => `
        <button class="rail-item" type="button" data-artifact-id="${escapeHtml(a.id)}">
          <strong>${escapeHtml(truncate(a.artifact_kind?.replaceAll("_", " ") || "Artifact", 36))}</strong>
          <span class="detail-meta">${escapeHtml(truncate(a.preview || "", 60))}</span>
        </button>
      `).join("")
    : `<p class="empty-state">Generate artifacts in Studio.</p>`;
}

// ── Right evidence rail ───────────────────────────────────────────────────────
export function renderEvidenceRail() {
  const rail = state.workspaceV2.right_rail || {};

  // Momentum
  const momentum = state.workspace.momentum || buildDefaultMomentum();
  document.getElementById("momentumScoreBadge").textContent = Math.round(momentum.momentum_score || 0);
  document.getElementById("momentumHeadline").textContent = momentum.headline;
  document.getElementById("momentumReason").textContent = momentum.reason;

  document.getElementById("momentumSignals").innerHTML = momentum.signals?.length
    ? momentum.signals.map((s) => `<span class="signal-pill">${escapeHtml(s)}</span>`).join("")
    : `<span class="signal-pill">No signals yet</span>`;

  document.getElementById("momentumActions").innerHTML = momentum.actions?.length
    ? momentum.actions.map((a, i) => `
        <button class="${i === 0 ? "action-pill primary-pill" : "action-pill"}" type="button"
          data-momentum-index="${i}">${escapeHtml(a.label)}</button>
      `).join("")
    : `<button class="action-pill primary-pill" type="button" data-momentum-index="0">Upload a source</button>`;

  // Evidence list
  const evidence = state.latestTutorResponse?.evidence?.length
    ? state.latestTutorResponse.evidence
    : (state.evidenceRailItems.length ? state.evidenceRailItems : (rail.evidence || []));
  document.getElementById("evidenceCountLabel").textContent = evidence.length;
  document.getElementById("evidenceList").innerHTML = evidence.length
    ? evidence.map((ev) => `
        <div class="evidence-item">
          <div class="evidence-label">${escapeHtml(ev.label || ev.excerpt || "Source evidence")}</div>
          <p class="evidence-snippet">${escapeHtml(ev.anchor_text || ev.excerpt || "No excerpt available yet.")}</p>
          <div class="evidence-meta">${escapeHtml(ev.document_name || "")}${ev.page_num ? ` · p${ev.page_num}` : ""}</div>
          <div class="evidence-actions">
            <button class="evidence-action" type="button" data-ev-action="cite" data-ev-id="${escapeHtml(ev.id || "")}">Cite</button>
            <button class="evidence-action" type="button" data-ev-action="note" data-ev-id="${escapeHtml(ev.id || "")}">Note</button>
            <button class="evidence-action" type="button" data-ev-action="card" data-ev-id="${escapeHtml(ev.id || "")}">Card</button>
          </div>
        </div>
      `).join("")
    : `<p class="empty-state">Evidence from tutor responses appears here.</p>`;

  // Confidence
  const conf = rail.confidence || {};
  document.getElementById("modelConfidenceLabel").textContent = conf.model != null
    ? `Model ${Math.round(conf.model * 100)}%`
    : "Model —";
  document.getElementById("learnerConfidenceLabel").textContent = `You ${state.confidence}%`;

  // Contradictions
  document.getElementById("contradictionsList").innerHTML = rail.contradictions?.length
    ? rail.contradictions.map((c) => `
        <div class="synthesis-item">
          <strong>${escapeHtml(c.label || c.concept_name)}</strong>
          <p>${escapeHtml(c.detail || "Cross-source conflict detected.")}</p>
        </div>
      `).join("")
    : `<p class="empty-state">No contradictions flagged at current scope.</p>`;

  // Related concepts
  document.getElementById("relatedConceptsList").innerHTML = rail.related_concepts?.length
    ? rail.related_concepts.map((c) => `
        <div class="related-concept">
          <div>
            <strong>${escapeHtml(c.name)}</strong>
            <p class="detail-meta">${escapeHtml(c.description || "")}</p>
          </div>
          <span class="detail-meta">${Math.round((c.mastery || 0) * 100)}% mastery</span>
        </div>
      `).join("")
    : `<p class="empty-state">Related concepts will appear here.</p>`;

  // Next actions
  document.getElementById("nextActionsList").innerHTML = rail.next_actions?.length
    ? rail.next_actions.map((a) => `
        <button class="action-pill" type="button" data-action-type="${escapeHtml(a.type || "")}"
          data-action-concept="${escapeHtml(a.concept_id || "")}">
          ${escapeHtml(a.label)}
        </button>
      `).join("")
    : `<p class="empty-state">Next best actions will appear here.</p>`;

  // Timeline
  const timeline = state.workspace.timeline || [];
  document.getElementById("timelineList").innerHTML = timeline.length
    ? timeline.slice(0, 12).map((item) => `
        <li class="timeline-item">
          <div class="timeline-dot"></div>
          <div>
            <strong>${escapeHtml(eventLabel(item.event_type))}</strong>
            <p>${escapeHtml(item.concept_name || item.document_name || "Workspace")}</p>
            <small>${escapeHtml(String(item.created_at || "").replace("T", " ").slice(0, 16))}</small>
          </div>
        </li>
      `).join("")
    : `<li class="empty-state">Activity will appear as you study.</li>`;
}

// ── Tutor surface ─────────────────────────────────────────────────────────────
export function renderTutorFeed() {
  const feed = document.getElementById("tutorFeed");
  if (!state.tutorMessages.length) {
    feed.innerHTML = `
      <article class="tutor-message assistant">
        <span class="message-meta">Grounded tutor</span>
        <p>Ask a question about your selected source. I'll answer with citations, scaffolds, and misconception checks.</p>
      </article>`;
    return;
  }

  feed.innerHTML = state.tutorMessages.map((msg, mi) => {
    const citations = msg.citations || [];
    const citationHtml = citations.length
      ? `<div class="citation-chip-list">${citations.map((cit, ci) => `
          <button class="citation-chip" type="button"
            data-message-index="${mi}" data-citation-index="${ci}">
            ${escapeHtml(cit.label)}
          </button>`).join("")}</div>`
      : "";
    const badge = msg.confidence != null
      ? `<span class="message-badge">Confidence ${Math.round(msg.confidence)}%</span>`
      : "";
    return `
      <article class="tutor-message ${escapeHtml(msg.role)}">
        <div class="message-header">
          <span class="message-meta">${msg.role === "assistant" ? "Grounded tutor" : "You"}</span>
          ${badge}
        </div>
        <div class="message-body">${msg.role === "assistant" ? renderMarkdown(msg.text) : escapeHtml(msg.text)}</div>
        ${citationHtml}
      </article>`;
  }).join("");
  feed.scrollTop = feed.scrollHeight;
}

export function renderTutorSupport() {
  const scaffolds = state.latestTutorResponse?.scaffolds || [];
  const misconceptions = state.latestTutorResponse?.misconceptions || [];

  document.getElementById("scaffoldList").innerHTML = scaffolds.length
    ? scaffolds.map((s) => `<li>${escapeHtml(s)}</li>`).join("")
    : `<li class="empty-state">Scaffolded steps appear after a tutor response.</li>`;
  document.getElementById("misconceptionList").innerHTML = misconceptions.length
    ? misconceptions.map((m) => `<li>${escapeHtml(m)}</li>`).join("")
    : `<li class="empty-state">Misconception watch is active.</li>`;

  const bar = document.getElementById("selectedTextBar");
  bar.classList.toggle("hidden", !state.selectedText);
  const label = document.getElementById("selectedTextLabel");
  if (label) label.textContent = state.selectedText ? truncate(state.selectedText, 220) : "";

  const evaluation = state.latestEvaluation;
  document.getElementById("tutorEvaluationPanel").innerHTML = evaluation
    ? `<article class="generated-card">
        <strong>${escapeHtml(evaluation.classification.replaceAll("_", " "))}</strong>
        <p>${escapeHtml(evaluation.repair_path.next_action)}</p>
        <small>Revisit in ${escapeHtml(String(evaluation.revisit.schedule_in_minutes))} minutes</small>
      </article>`
    : `<p class="empty-state">Self-check diagnosis appears after evaluation.</p>`;
}

// ── Review surface ────────────────────────────────────────────────────────────
export function renderReviewSurface() {
  const queue = state.reviewQueue || [];
  const total = queue.length;
  const done = Math.max(0, (state._reviewDone || 0));

  document.getElementById("reviewProgressLabel").textContent = `${done} / ${done + total}`;
  const fill = document.getElementById("reviewProgressFill");
  if (fill) {
    fill.style.width = `${done + total > 0 ? Math.round((done / (done + total)) * 100) : 0}%`;
  }

  document.getElementById("reviewQueue").innerHTML = queue.length
    ? queue.map((item, i) => `
        <article class="review-card ${i === 0 ? "active-card" : ""}">
          <p class="review-question">${escapeHtml(item.front)}</p>
          <div class="review-meta">${escapeHtml(item.concept_name)} · ${escapeHtml(item.source_name)}</div>
          <small>Due ${escapeHtml(item.due_date || "now")} · recall ${Math.round((item.mastery_state?.recall_score || 0) * 100)}%</small>
          ${i === 0 ? `
            <div class="button-row compact" style="margin-top:.75rem">
              <button class="ghost-button" type="button" data-review-outcome="missed">Missed it</button>
              <button class="primary-button" type="button" data-review-outcome="got_it">Got it</button>
            </div>
          ` : ""}
        </article>
      `).join("")
    : `<p class="empty-state">No cards due right now. Great work!</p>`;
}

// ── Session surface ───────────────────────────────────────────────────────────
export function renderSessionSurface() {
  const activeSession = state.activeSession;
  document.getElementById("activeSessionPanel").innerHTML = activeSession
    ? `<article class="generated-card">
        <strong>${escapeHtml(activeSession.objective || "Focus sprint")}</strong>
        <p>${escapeHtml(activeSession.mode)} · ${escapeHtml(String(activeSession.duration_minutes))} min</p>
        <small>Status: ${escapeHtml(activeSession.status)}</small>
      </article>`
    : `<p class="empty-state">No active session. Configure and start one above.</p>`;

  const summary = state.sessionSummary;
  document.getElementById("sessionSummaryPanel").innerHTML = summary
    ? `<article class="generated-card">
        <strong>Mastery Δ ${escapeHtml(String(summary.mastery_delta || 0))}</strong>
        <p>${escapeHtml(summary.revision_recommendation || "Good work this session.")}</p>
        <small>${escapeHtml(summary.stretch_question || "")}</small>
      </article>`
    : `<p class="empty-state">Summary appears after session completion.</p>`;

  const recentSessions = state.workspaceV2.left_rail?.sessions || [];
  document.getElementById("recentSessionsList").innerHTML = recentSessions.length
    ? recentSessions.map((s) => `
        <div class="rail-item">
          <strong>${escapeHtml(truncate(s.objective || "Session", 40))}</strong>
          <span class="detail-meta">${escapeHtml(s.status || "")} · ${s.duration_minutes || 25}m</span>
        </div>
      `).join("")
    : `<p class="empty-state">Past sessions appear here.</p>`;
}

// ── Notes surface ─────────────────────────────────────────────────────────────
export function renderNotesSurface() {
  const titleInput = document.getElementById("noteTitleInput");
  const editor = document.getElementById("noteEditor");
  if (document.activeElement !== titleInput) titleInput.value = state.noteDraft.title;
  if (document.activeElement !== editor) editor.value = state.noteDraft.content;

  document.getElementById("noteSourceSnippet").textContent = state.noteDraft.sourceSnippet
    || state.selectedText
    || "Select source text or ask the tutor to anchor this note.";

  document.getElementById("noteFlashcards").innerHTML = state.noteTransforms.flashcards.length
    ? state.noteTransforms.flashcards.map((card) => `
        <article class="generated-card">
          <strong>${escapeHtml(card.front)}</strong>
          <p>${escapeHtml(card.back)}</p>
        </article>`).join("")
    : `<p class="empty-state">Generate flashcards from this note.</p>`;

  document.getElementById("noteQuiz").innerHTML = state.noteTransforms.quiz.length
    ? state.noteTransforms.quiz.map((q) => `
        <article class="generated-card">
          <strong>${escapeHtml(q.question)}</strong>
          <p>${escapeHtml(q.answer)}</p>
        </article>`).join("")
    : `<p class="empty-state">Quiz drafts appear after transformation.</p>`;

  const notes = state.workspace.notes || [];
  const filterType = document.getElementById("noteFilterType")?.value || "";
  const filtered = filterType ? notes.filter((n) => n.note_type === filterType) : notes;
  document.getElementById("recentNotesCount").textContent = `${filtered.length} note${filtered.length === 1 ? "" : "s"}`;
  document.getElementById("recentNotesList").innerHTML = filtered.length
    ? filtered.map((note) => `
        <button class="recent-note rail-item" type="button" data-note-id="${escapeHtml(note.id)}">
          <strong>${escapeHtml(note.title)}</strong>
          <span class="detail-meta note-type-badge">${escapeHtml((note.note_type || "note").replaceAll("_", " "))}</span>
          <p>${escapeHtml(truncate(note.content, 120))}</p>
        </button>`).join("")
    : `<p class="empty-state">Saved notes appear here.</p>`;
}

// ── Compare surface ───────────────────────────────────────────────────────────
export function renderCompareSurface() {
  const options = compareConceptOptions();
  const optHtml = options.length
    ? options.map((o) => `
        <option value="${escapeHtml(o.id)}" title="${escapeHtml(o.description || "")}">
          ${escapeHtml(o.name)}
        </option>`).join("")
    : `<option value="">No concepts available</option>`;

  const leftSel = document.getElementById("compareLeftSelect");
  const rightSel = document.getElementById("compareRightSelect");
  leftSel.innerHTML = optHtml;
  rightSel.innerHTML = optHtml;
  leftSel.disabled = !options.length;
  rightSel.disabled = !options.length;
  if (state.compareLeftId) leftSel.value = state.compareLeftId;
  if (state.compareRightId) rightSel.value = state.compareRightId;

  document.getElementById("compareSimilarities").innerHTML = state.compare?.similarities?.length
    ? state.compare.similarities.map((s) => `<li>${escapeHtml(s)}</li>`).join("")
    : `<li class="empty-state">Choose two concepts to compare.</li>`;
  document.getElementById("compareDifferences").innerHTML = state.compare?.differences?.length
    ? state.compare.differences.map((d) => `<li>${escapeHtml(d)}</li>`).join("")
    : `<li class="empty-state">Contrasts will appear here.</li>`;
  document.getElementById("comparePrompt").textContent = state.compare?.study_prompt
    || "Choose two concepts to generate a contrast prompt.";
  document.getElementById("compareCitationList").innerHTML = state.compare?.citations?.length
    ? state.compare.citations.map((cit, i) => `
        <button class="citation-chip" type="button" data-compare-citation-index="${i}">
          ${escapeHtml(cit.label)}
        </button>`).join("")
    : "";
}

// ── Studio surface ────────────────────────────────────────────────────────────
export function renderStudioSurface() {
  const artifact = state.studioArtifact;

  // Sync config selects with state (don't clobber user changes)
  const kindSel = document.getElementById("artifactKindSelect");
  const audSel = document.getElementById("artifactAudience");
  const depthSel = document.getElementById("artifactDepth");
  const lenSel = document.getElementById("artifactLength");
  const promptEl = document.getElementById("artifactCustomPrompt");
  if (kindSel && document.activeElement !== kindSel) kindSel.value = state.studioConfig.artifact_kind;
  if (audSel && document.activeElement !== audSel) audSel.value = state.studioConfig.audience;
  if (depthSel && document.activeElement !== depthSel) depthSel.value = state.studioConfig.depth;
  if (lenSel && document.activeElement !== lenSel) lenSel.value = state.studioConfig.output_length;
  if (promptEl && document.activeElement !== promptEl) promptEl.value = state.studioConfig.custom_prompt;

  const output = document.getElementById("studioOutput");
  if (artifact) {
    output.innerHTML = `
      <div class="artifact-meta">
        <strong>${escapeHtml(artifact.artifact_kind?.replaceAll("_", " ") || "Artifact")}</strong>
        <span class="detail-meta">${escapeHtml(artifact.generator || "")}</span>
      </div>
      <div class="artifact-body markdown-output">${renderMarkdown(artifact.content || "")}</div>`;
  } else {
    output.innerHTML = `<p class="empty-state">Configure and click Generate to build a study artifact from your sources.</p>`;
  }

  const recentList = document.getElementById("recentArtifactsList");
  const artifacts = state.workspaceV2.left_rail?.artifacts || [];
  recentList.innerHTML = artifacts.length
    ? artifacts.map((a) => `
        <button class="rail-item" type="button" data-load-artifact="${escapeHtml(a.id)}">
          <strong>${escapeHtml(a.artifact_kind?.replaceAll("_", " ") || "Artifact")}</strong>
          <p class="detail-meta">${escapeHtml(truncate(a.preview || "", 80))}</p>
        </button>`).join("")
    : `<p class="empty-state">Generated artifacts appear here.</p>`;
}

// ── Synthesis surface ─────────────────────────────────────────────────────────
export function renderSynthesisSurface() {
  const result = state.synthesisResult;
  const output = document.getElementById("synthesisOutput");

  if (result?.agreement) {
    const ag = result.agreement;
    output.innerHTML = `
      <div class="synthesis-summary">
        <strong>${ag.shared_concepts?.length || 0} shared concepts across ${ag.source_count || 0} sources</strong>
        ${ag.themes?.length ? `<p>Dominant themes: ${escapeHtml(ag.themes.slice(0, 6).join(", "))}</p>` : ""}
      </div>`;
  } else if (result?.terminology?.length) {
    output.innerHTML = `<p class="empty-state">Terminology alignment found ${result.terminology.length} term pairs.</p>`;
  } else {
    output.innerHTML = `<p class="empty-state">Run Synthesis to compare your sources. Select sources in the left rail first.</p>`;
  }

  const contradictions = result?.contradictions || state.workspaceV2.right_rail?.contradictions || [];
  document.getElementById("synthesisContradictions").innerHTML = contradictions.length
    ? contradictions.map((c) => `
        <div class="synthesis-item">
          <strong>${escapeHtml(c.concept_name || c.label || "Concept")}</strong>
          <span class="severity-badge">${escapeHtml(c.severity || "medium")}</span>
          <p>Sources: ${escapeHtml(c.source_a_name || "")} vs ${escapeHtml(c.source_b_name || "")}</p>
          <small>Overlap: ${Math.round((c.overlap_score || 0) * 100)}%</small>
        </div>`).join("")
    : `<p class="empty-state">No contradictions detected yet.</p>`;

  const shared = result?.agreement?.shared_concepts || [];
  document.getElementById("synthesisAgreements").innerHTML = shared.length
    ? shared.slice(0, 10).map((c) => `
        <div class="synthesis-item"><strong>${escapeHtml(c.name)}</strong>
          <span class="detail-meta">in ${c.source_count || 1} sources</span>
        </div>`).join("")
    : `<p class="empty-state">Shared themes appear after synthesis.</p>`;

  const gaps = result?.gaps || [];
  document.getElementById("synthesisGaps").innerHTML = gaps.length
    ? gaps.slice(0, 8).map((g) => `
        <div class="synthesis-item">
          <strong>${escapeHtml(g.concept_name || g.name)}</strong>
          <p>Present in ${g.present_in?.length || 0} source(s), missing from ${g.missing_in?.length || 0}.</p>
        </div>`).join("")
    : `<p class="empty-state">Gap analysis appears after synthesis.</p>`;
}

// ── Render all ────────────────────────────────────────────────────────────────
export function renderWorkspace() {
  document.querySelector(".os-shell").classList.toggle("focus-mode", state.focusMode);
  const focusBtn = document.getElementById("focusModeToggle");
  if (focusBtn) focusBtn.textContent = state.focusMode ? "Exit Focus" : "Focus";

  renderHeaderStats();
  renderScopeSelects();
  renderSourceRail();
  renderEvidenceRail();
  renderTutorFeed();
  renderTutorSupport();
  renderReviewSurface();
  renderSessionSurface();
  renderNotesSurface();
  renderCompareSurface();
  renderStudioSurface();
  renderSynthesisSurface();
}

// ── Helpers exported for main.js ──────────────────────────────────────────────
export function previewCitationFromResponse(response) {
  if (response.citations?.length) {
    setPreviewFromCitation(response.citations[0]);
  }
}

export function fillNoteFromRecent(note) {
  state.noteDraft = {
    noteId: note.id,
    title: note.title || defaultNoteTitle(),
    content: note.content || "",
    sourceSnippet: note.source_snippet || ""
  };
}

/** No-op shim kept for bootstrap.js compatibility */
export function renderPreview() {}
export function renderHeaderStats2() {}
