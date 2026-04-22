import { escapeHtml, formatDocumentMeta, state } from "../state.js";

export function renderLibrary(onDocumentSelect) {
  const list = document.getElementById("documentList");
  const title = document.getElementById("documentDetailTitle");
  const meta = document.getElementById("documentDetailMeta");
  const summary = document.getElementById("documentSummary");
  const conceptList = document.getElementById("documentConceptList");
  const questionList = document.getElementById("documentQuestionList");
  const chunkList = document.getElementById("documentChunkList");
  const deleteButton = document.getElementById("deleteDocumentBtn");

  document.getElementById("libraryCount").textContent = `${state.documents.length} file${state.documents.length === 1 ? "" : "s"}`;
  list.innerHTML = "";
  deleteButton.disabled = !state.documentDetail;

  if (!state.documents.length) {
    list.innerHTML = `<p class="empty-state">No documents yet. Upload a TXT, MD, or PDF file to start building your library.</p>`;
  } else {
    state.documents.forEach((docItem) => {
      const button = window.document.createElement("button");
      button.className = `document-button${state.selectedDocumentId === docItem.id ? " active" : ""}`;
      button.type = "button";
      button.innerHTML = `
        <strong>${escapeHtml(docItem.filename)}</strong>
        <small>${escapeHtml(formatDocumentMeta(docItem))}</small>
        <p>${escapeHtml(docItem.summary || "No summary available yet.")}</p>
        <small>${docItem.concept_count} concepts · ${docItem.question_count} questions</small>
      `;
      button.addEventListener("click", () => onDocumentSelect(docItem.id));
      list.appendChild(button);
    });
  }

  if (!state.documentDetail) {
    title.textContent = "Select a document";
    meta.textContent = "Your uploaded files will appear here.";
    summary.textContent = "Click a file on the left to inspect the extracted concepts, generated questions, and document sections.";
    document.getElementById("documentSubjectName").textContent = "General";
    document.getElementById("documentChunkCount").textContent = "0";
    document.getElementById("documentConceptCount").textContent = "0";
    document.getElementById("documentQuestionCount").textContent = "0";
    document.getElementById("documentSubjectInput").value = "";
    conceptList.innerHTML = `<li class="empty-state">No document selected.</li>`;
    questionList.innerHTML = `<li class="empty-state">No document selected.</li>`;
    chunkList.innerHTML = `<p class="empty-state">No extracted sections yet.</p>`;
    return;
  }

  const { document: selectedDoc, counts, concepts, questions, chunks } = state.documentDetail;
  title.textContent = selectedDoc.filename;
  meta.textContent = formatDocumentMeta(selectedDoc);
  summary.textContent = state.documentDetail.summary;
  document.getElementById("documentSubjectName").textContent = selectedDoc.subject_name || "General";
  document.getElementById("documentSubjectInput").value = selectedDoc.subject_name || "";
  document.getElementById("documentChunkCount").textContent = counts.chunks;
  document.getElementById("documentConceptCount").textContent = counts.concepts;
  document.getElementById("documentQuestionCount").textContent = counts.questions;

  conceptList.innerHTML = concepts.length
    ? concepts.map((concept) => `<li><strong>${escapeHtml(concept.display_name || concept.name)}</strong><br />${escapeHtml(concept.description)}<br /><small>${escapeHtml(concept.document_name)} · ${escapeHtml(concept.subject_name)}</small></li>`).join("")
    : `<li class="empty-state">No concepts extracted.</li>`;

  questionList.innerHTML = questions.length
    ? questions.map((question) => `<li><strong>${escapeHtml(question.concept)}</strong> · ${escapeHtml(question.difficulty)}<br />${escapeHtml(question.question)}</li>`).join("")
    : `<li class="empty-state">No generated questions yet.</li>`;

  chunkList.innerHTML = chunks.length
    ? chunks.map((chunk) => `
        <article class="chunk-item">
          <strong>${escapeHtml(chunk.section || `Section ${chunk.chunk_index + 1}`)}</strong>
          <small>${chunk.token_count} tokens</small>
          <p>${escapeHtml(chunk.content)}</p>
        </article>
      `).join("")
    : `<p class="empty-state">No extracted sections yet.</p>`;
}
