import {
  escapeHtml,
  graphDocuments,
  shortFileLabel,
  state,
  truncate
} from "../state.js";

const SVG_NS = "http://www.w3.org/2000/svg";
const VIEWBOX = { width: 760, height: 420 };
const NODE_WIDTH = 182;
const NODE_HEIGHT = 112;
const EDGE_LABEL_LIMIT = 18;

const graphUi = {
  scale: 1,
  tx: 0,
  ty: 0,
  hoveredId: null,
  signature: "",
  stageBound: false,
  viewportGroup: null,
  nodeElements: new Map(),
  edgeElements: [],
  context: null,
  callbacks: {},
  pan: null
};

function clamp(value, min, max) {
  return Math.max(min, Math.min(max, value));
}

function svgElement(tagName, attributes = {}) {
  const element = document.createElementNS(SVG_NS, tagName);
  Object.entries(attributes).forEach(([name, value]) => {
    element.setAttribute(name, String(value));
  });
  return element;
}

function percentLabel(value) {
  return `${Math.round(clamp(Number(value) || 0, 0, 1) * 100)}%`;
}

function masteryTone(concept) {
  const mastery = Number(concept?.mastery) || 0;
  if (mastery >= 0.75) {
    return { label: "Strong", css: "strong", color: "#0f766e" };
  }
  if (mastery >= 0.45) {
    return { label: "Building", css: "building", color: "#d97706" };
  }
  return { label: "Needs review", css: "fragile", color: "#b42318" };
}

function wrapLabel(text, maxLines = 2, maxChars = 18) {
  const words = String(text || "Untitled concept").split(/\s+/).filter(Boolean);
  if (!words.length) {
    return ["Untitled concept"];
  }

  const lines = [];
  let current = "";

  words.forEach((word) => {
    const next = current ? `${current} ${word}` : word;
    if (next.length <= maxChars || !current) {
      current = next;
      return;
    }
    lines.push(current);
    current = word;
  });

  if (current) {
    lines.push(current);
  }

  if (lines.length <= maxLines) {
    return lines;
  }

  const trimmed = lines.slice(0, maxLines);
  trimmed[maxLines - 1] = truncate(trimmed[maxLines - 1], maxChars);
  return trimmed;
}

function relationLabel(value) {
  return truncate(String(value || "Related").replaceAll("_", " "), EDGE_LABEL_LIMIT);
}

function graphSignature() {
  const nodeKey = state.graph.nodes.map((node) => node.id).join("|");
  const edgeKey = state.graph.edges.map((edge) => `${edge.source}:${edge.target}:${edge.relationship}`).join("|");
  return `${state.graphFilters.subjectName}::${state.graphFilters.docId}::${nodeKey}::${edgeKey}`;
}

function layoutNodes() {
  const degrees = new Map(state.graph.nodes.map((node) => [node.id, 0]));
  state.graph.edges.forEach((edge) => {
    degrees.set(edge.source, (degrees.get(edge.source) || 0) + 1);
    degrees.set(edge.target, (degrees.get(edge.target) || 0) + 1);
  });

  const positioned = state.graph.nodes
    .map((node) => ({ ...node }))
    .sort((left, right) => {
      const degreeDelta = (degrees.get(right.id) || 0) - (degrees.get(left.id) || 0);
      if (degreeDelta) {
        return degreeDelta;
      }
      const masteryDelta = (Number(right.mastery) || 0) - (Number(left.mastery) || 0);
      if (masteryDelta) {
        return masteryDelta;
      }
      return String(left.label || "").localeCompare(String(right.label || ""));
    });

  if (positioned.length === 1) {
    positioned[0].x = VIEWBOX.width / 2;
    positioned[0].y = VIEWBOX.height / 2;
    return positioned;
  }

  const columns = clamp(Math.ceil(Math.sqrt(positioned.length)), 2, 5);
  const horizontalGap = NODE_WIDTH + 42;
  const verticalGap = NODE_HEIGHT + 54;
  const rows = [];

  for (let index = 0; index < positioned.length; index += columns) {
    rows.push(positioned.slice(index, index + columns));
  }

  const middleRow = (rows.length - 1) / 2;
  rows.forEach((row, rowIndex) => {
    const rowWidth = (row.length - 1) * horizontalGap;
    const baseX = VIEWBOX.width / 2 - rowWidth / 2;
    const baseY = VIEWBOX.height / 2 + (rowIndex - middleRow) * verticalGap;
    row.forEach((node, columnIndex) => {
      node.x = baseX + columnIndex * horizontalGap;
      node.y = baseY + ((rowIndex + columnIndex) % 2 === 0 ? -10 : 10);
    });
  });

  return positioned;
}

function buildGraphContext() {
  const nodes = layoutNodes();
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const relatedIds = new Map(nodes.map((node) => [node.id, new Set()]));

  state.graph.edges.forEach((edge) => {
    relatedIds.get(edge.source)?.add(edge.target);
    relatedIds.get(edge.target)?.add(edge.source);
  });

  return {
    nodes,
    nodesById,
    relatedIds
  };
}

function graphFocusId() {
  return graphUi.hoveredId || state.selectedConceptId || null;
}

function graphNodes() {
  return graphUi.context?.nodes || state.graph.nodes;
}

function selectedGraphConcept() {
  return graphNodes().find((node) => node.id === state.selectedConceptId) || null;
}

function hoverGraphConcept() {
  return graphNodes().find((node) => node.id === graphUi.hoveredId) || null;
}

function defaultHoverCopy() {
  const total = graphNodes().length;
  if (!total) {
    return {
      eyebrow: "Map focus",
      title: "No concepts available",
      meta: "Upload or select a source to populate the graph.",
      description: "Once concepts are extracted, this panel will show structure, mastery, and the next study move."
    };
  }
  return {
    eyebrow: "Map focus",
    title: "Inspect the learning graph",
    meta: `${total} concept${total === 1 ? "" : "s"} in view. Hover to inspect, click to pin, drag to pan, and scroll to zoom.`,
    description: "The map highlights what is solid, what is still forming, and which ideas should branch into tutor, review, or compare."
  };
}

function conceptMeta(concept, context) {
  if (!concept) {
    return null;
  }
  const relatedCount = context.relatedIds.get(concept.id)?.size || 0;
  const tone = masteryTone(concept);
  return {
    tone,
    mastery: percentLabel(concept.mastery),
    relatedCount,
    sourceCount: 1,
    fileLabel: shortFileLabel(concept.document_name),
    subjectName: concept.subject_name || "General"
  };
}

function updateHovercard(context) {
  const hovered = hoverGraphConcept();
  const selected = selectedGraphConcept();
  const active = hovered || selected;
  if (!active) return;

  const details = conceptMeta(active, context);
  const titleEl = document.getElementById("conceptTitle");
  const explEl = document.getElementById("conceptExplanation");
  const takeEl = document.getElementById("conceptTakeaway");
  if (titleEl) titleEl.textContent = active.label;
  if (explEl) explEl.textContent = active.description ? truncate(active.description, 220) : `${details.fileLabel} · ${details.subjectName}`;
  if (takeEl) takeEl.textContent = `${details.tone.label} · ${details.mastery} mastery · ${details.relatedCount} linked`;

  const masteryDetail = document.getElementById("conceptMasteryDetail");
  if (masteryDetail) {
    masteryDetail.innerHTML = `
      <div class="mastery-bar-row">
        <div class="mastery-bar-head"><strong>${escapeHtml(details.tone.label)}</strong><span>${escapeHtml(details.mastery)}</span></div>
        <div class="mini-progress"><span style="width:${escapeHtml(details.mastery)}"></span></div>
      </div>`;
  }
}

function updateSelectionBar(context) {
  const concept = selectedGraphConcept();
  const hasSelection = !!concept;
  ["teachConceptBtn", "quizConceptBtn", "addConceptNoteBtn", "compareConceptBtn"].forEach((id) => {
    const el = document.getElementById(id);
    if (el) el.disabled = !hasSelection;
  });
  if (!concept) return;
  const details = conceptMeta(concept, context);
  const titleEl = document.getElementById("conceptTitle");
  if (titleEl) titleEl.textContent = concept.label;
  const explEl = document.getElementById("conceptExplanation");
  if (explEl) explEl.textContent = concept.description ? truncate(concept.description, 220) : `${details.fileLabel} · ${details.subjectName}`;
}

function updateConceptMetaChips(context) {
  const concept = selectedGraphConcept();
  const masteryDetail = document.getElementById("conceptMasteryDetail");
  if (!masteryDetail || !concept) return;
  const details = conceptMeta(concept, context);
  masteryDetail.innerHTML = `
    <div class="mastery-bar-row">
      <div class="mastery-bar-head">
        <strong>${escapeHtml(details.tone.label)}</strong>
        <span>${escapeHtml(details.mastery)}</span>
      </div>
      <div class="mini-progress"><span style="width:${escapeHtml(details.mastery)}"></span></div>
    </div>
    <p class="detail-meta">${escapeHtml(details.fileLabel)} · ${escapeHtml(details.subjectName)} · ${details.relatedCount} linked</p>
  `;
}

function updateGraphFocus(context) {
  const focusId = graphFocusId();
  const relatedSet = focusId ? (context.relatedIds.get(focusId) || new Set()) : new Set();

  graphUi.nodeElements.forEach((group, nodeId) => {
    group.classList.toggle("is-selected", nodeId === state.selectedConceptId);
    group.classList.toggle("is-hovered", nodeId === graphUi.hoveredId);
    group.classList.toggle("is-related", !!focusId && relatedSet.has(nodeId));
    group.classList.toggle("is-dimmed", !!focusId && nodeId !== focusId && nodeId !== state.selectedConceptId && !relatedSet.has(nodeId));
  });

  graphUi.edgeElements.forEach(({ edge, elements }) => {
    const isActive = !!focusId && (edge.source === focusId || edge.target === focusId);
    elements.group.classList.toggle("is-active", isActive);
    elements.group.classList.toggle("is-dimmed", !!focusId && !isActive);
  });

  updateHovercard(context);
  updateSelectionBar(context);
  updateConceptMetaChips(context);
}

function applyViewport() {
  const zoomLabel = document.getElementById("graphZoomLabel");
  if (zoomLabel) {
    zoomLabel.textContent = `${Math.round(graphUi.scale * 100)}%`;
  }
  if (!graphUi.viewportGroup) {
    return;
  }
  graphUi.viewportGroup.setAttribute(
    "transform",
    `matrix(${graphUi.scale} 0 0 ${graphUi.scale} ${graphUi.tx} ${graphUi.ty})`
  );
}

function fitViewport() {
  const nodes = graphNodes();
  if (!nodes.length) {
    graphUi.scale = 1;
    graphUi.tx = 0;
    graphUi.ty = 0;
    applyViewport();
    return;
  }

  const margin = 42;
  const minX = Math.min(...nodes.map((node) => node.x - NODE_WIDTH / 2));
  const maxX = Math.max(...nodes.map((node) => node.x + NODE_WIDTH / 2));
  const minY = Math.min(...nodes.map((node) => node.y - NODE_HEIGHT / 2));
  const maxY = Math.max(...nodes.map((node) => node.y + NODE_HEIGHT / 2));
  const contentWidth = Math.max(maxX - minX, 1);
  const contentHeight = Math.max(maxY - minY, 1);
  const scaleX = (VIEWBOX.width - margin * 2) / contentWidth;
  const scaleY = (VIEWBOX.height - margin * 2) / contentHeight;

  graphUi.scale = clamp(Math.min(scaleX, scaleY, 1.2), 0.72, 1.25);
  graphUi.tx = (VIEWBOX.width - contentWidth * graphUi.scale) / 2 - minX * graphUi.scale;
  graphUi.ty = (VIEWBOX.height - contentHeight * graphUi.scale) / 2 - minY * graphUi.scale;
  applyViewport();
}

function eventToSvgPoint(event, svg) {
  const rect = svg.getBoundingClientRect();
  const x = ((event.clientX - rect.left) / rect.width) * VIEWBOX.width;
  const y = ((event.clientY - rect.top) / rect.height) * VIEWBOX.height;
  return { x, y };
}

function zoomAt(svgPoint, delta) {
  const nextScale = clamp(graphUi.scale * delta, 0.72, 1.6);
  const sceneX = (svgPoint.x - graphUi.tx) / graphUi.scale;
  const sceneY = (svgPoint.y - graphUi.ty) / graphUi.scale;
  graphUi.scale = nextScale;
  graphUi.tx = svgPoint.x - sceneX * graphUi.scale;
  graphUi.ty = svgPoint.y - sceneY * graphUi.scale;
  applyViewport();
}

function callGraphAction(callback, concept) {
  if (!callback || !concept) {
    return;
  }
  Promise.resolve(callback(concept)).catch((error) => {
    console.error(error);
  });
}

function bindStageInteractions() {
  if (graphUi.stageBound) {
    return;
  }

  const svg = document.getElementById("conceptMap");
  // Use SVG as both stage and event target (no separate graphStage wrapper in new layout)
  const stage = svg;

  stage.addEventListener("wheel", (event) => {
    if (!state.graph.nodes.length) return;
    event.preventDefault();
    const svgPoint = eventToSvgPoint(event, svg);
    zoomAt(svgPoint, event.deltaY > 0 ? 0.92 : 1.08);
  }, { passive: false });

  stage.addEventListener("pointerdown", (event) => {
    const clickedNode = event.target.closest?.("[data-node-id]");
    if (clickedNode || !state.graph.nodes.length) return;
    const rect = svg.getBoundingClientRect();
    graphUi.pan = {
      pointerId: event.pointerId,
      clientX: event.clientX,
      clientY: event.clientY,
      tx: graphUi.tx,
      ty: graphUi.ty,
      rectWidth: rect.width,
      rectHeight: rect.height
    };
    stage.classList.add("is-panning");
    stage.setPointerCapture(event.pointerId);
  });

  stage.addEventListener("pointermove", (event) => {
    if (!graphUi.pan || graphUi.pan.pointerId !== event.pointerId) return;
    const dx = ((event.clientX - graphUi.pan.clientX) / graphUi.pan.rectWidth) * VIEWBOX.width;
    const dy = ((event.clientY - graphUi.pan.clientY) / graphUi.pan.rectHeight) * VIEWBOX.height;
    graphUi.tx = graphUi.pan.tx + dx;
    graphUi.ty = graphUi.pan.ty + dy;
    applyViewport();
  });

  const stopPanning = (event) => {
    if (!graphUi.pan || graphUi.pan.pointerId !== event.pointerId) return;
    stage.classList.remove("is-panning");
    graphUi.pan = null;
  };

  stage.addEventListener("pointerup", stopPanning);
  stage.addEventListener("pointercancel", stopPanning);
  stage.addEventListener("pointerleave", (event) => {
    if (graphUi.pan && graphUi.pan.pointerId === event.pointerId) {
      stage.classList.remove("is-panning");
      graphUi.pan = null;
    }
    if (!event.target.closest?.("[data-node-id]")) {
      graphUi.hoveredId = null;
      if (graphUi.context) updateGraphFocus(graphUi.context);
    }
  });

  graphUi.stageBound = true;
}

/** Called by main.js after binding concept action buttons */
export function setConceptCallbacks(callbacks) {
  graphUi.callbacks = { ...graphUi.callbacks, ...callbacks };
}

export function getSelectedConcept() {
  return selectedGraphConcept();
}

function anchorPoint(source, target) {
  const dx = target.x - source.x;
  const dy = target.y - source.y;
  const divisor = Math.max(Math.abs(dx) / (NODE_WIDTH / 2 - 16), Math.abs(dy) / (NODE_HEIGHT / 2 - 18), 1);
  return {
    x: source.x + dx / divisor,
    y: source.y + dy / divisor
  };
}

function quadraticPoint(start, control, end, t = 0.5) {
  const x = ((1 - t) ** 2) * start.x + 2 * (1 - t) * t * control.x + (t ** 2) * end.x;
  const y = ((1 - t) ** 2) * start.y + 2 * (1 - t) * t * control.y + (t ** 2) * end.y;
  return { x, y };
}

function appendTitleLines(group, lines, centerX, startY) {
  lines.forEach((line, index) => {
    const text = svgElement("text", {
      x: centerX,
      y: startY + index * 17,
      "text-anchor": "middle",
      class: "graph-node-title"
    });
    text.textContent = line;
    text.style.pointerEvents = "none";
    group.appendChild(text);
  });
}

function renderEdge(edge, index, context, group) {
  const source = context.nodesById.get(edge.source);
  const target = context.nodesById.get(edge.target);
  if (!source || !target) {
    return;
  }

  const start = anchorPoint(source, target);
  const end = anchorPoint(target, source);
  const dx = end.x - start.x;
  const dy = end.y - start.y;
  const distance = Math.max(Math.hypot(dx, dy), 1);
  const normal = { x: -dy / distance, y: dx / distance };
  const bend = Math.min(26, 10 + (index % 3) * 6);
  const control = {
    x: (start.x + end.x) / 2 + normal.x * bend,
    y: (start.y + end.y) / 2 + normal.y * bend
  };
  const path = svgElement("path", {
    d: `M ${start.x} ${start.y} Q ${control.x} ${control.y} ${end.x} ${end.y}`,
    class: `graph-edge ${edge.relationship === "relates to" ? "graph-edge-dashed" : ""}`
  });
  const midpoint = quadraticPoint(start, control, end, 0.5);
  const label = relationLabel(edge.relationship);
  const pillWidth = Math.max(86, label.length * 6.2 + 22);
  const pill = svgElement("rect", {
    x: midpoint.x - pillWidth / 2,
    y: midpoint.y - 13,
    width: pillWidth,
    height: 26,
    rx: 13,
    class: "graph-edge-pill"
  });
  const text = svgElement("text", {
    x: midpoint.x,
    y: midpoint.y + 4,
    "text-anchor": "middle",
    class: "graph-edge-label"
  });
  text.textContent = label;
  text.style.pointerEvents = "none";

  group.appendChild(path);
  group.appendChild(pill);
  group.appendChild(text);

  graphUi.edgeElements.push({
    edge,
    elements: { group, path, pill, text }
  });
}

function renderNode(concept, context, handlers, root) {
  const tone = masteryTone(concept);
  const group = svgElement("g", {
    class: `graph-node-group graph-node-${tone.css}`,
    "data-node-id": concept.id,
    tabindex: 0,
    role: "button",
    "aria-label": `${concept.label}, ${tone.label}, ${percentLabel(concept.mastery)} mastery`
  });
  const left = concept.x - NODE_WIDTH / 2;
  const top = concept.y - NODE_HEIGHT / 2;
  const relatedCount = context.relatedIds.get(concept.id)?.size || 0;
  const titleLines = wrapLabel(concept.label);
  const titleStartY = concept.y - (titleLines.length === 1 ? 8 : 16);

  group.appendChild(svgElement("rect", {
    x: left + 4,
    y: top + 8,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    rx: 26,
    class: "graph-node-shadow"
  }));
  group.appendChild(svgElement("rect", {
    x: left - 10,
    y: top - 10,
    width: NODE_WIDTH + 20,
    height: NODE_HEIGHT + 20,
    rx: 32,
    class: "graph-node-halo"
  }));
  group.appendChild(svgElement("rect", {
    x: left,
    y: top,
    width: NODE_WIDTH,
    height: NODE_HEIGHT,
    rx: 24,
    class: "graph-node-card"
  }));
  group.appendChild(svgElement("rect", {
    x: left + 16,
    y: top + 16,
    width: 72,
    height: 24,
    rx: 12,
    class: "graph-node-badge"
  }));

  const badgeLabel = svgElement("text", {
    x: left + 52,
    y: top + 31,
    "text-anchor": "middle",
    class: "graph-node-badge-label"
  });
  badgeLabel.textContent = tone.label;
  badgeLabel.style.pointerEvents = "none";
  group.appendChild(badgeLabel);

  appendTitleLines(group, titleLines, concept.x, titleStartY);

  const subtitle = svgElement("text", {
    x: concept.x,
    y: concept.y + 22,
    "text-anchor": "middle",
    class: "graph-node-subtitle"
  });
  subtitle.textContent = shortFileLabel(concept.document_name);
  subtitle.style.pointerEvents = "none";
  group.appendChild(subtitle);

  const meta = svgElement("text", {
    x: concept.x,
    y: concept.y + 39,
    "text-anchor": "middle",
    class: "graph-node-meta"
  });
  meta.textContent = `${percentLabel(concept.mastery)} mastery · ${relatedCount} linked`;
  meta.style.pointerEvents = "none";
  group.appendChild(meta);

  group.appendChild(svgElement("rect", {
    x: left + 16,
    y: top + NODE_HEIGHT - 22,
    width: NODE_WIDTH - 32,
    height: 8,
    rx: 4,
    class: "graph-node-track"
  }));
  group.appendChild(svgElement("rect", {
    x: left + 16,
    y: top + NODE_HEIGHT - 22,
    width: Math.max((NODE_WIDTH - 32) * clamp(Number(concept.mastery) || 0, 0.08, 1), 18),
    height: 8,
    rx: 4,
    class: "graph-node-fill"
  }));

  const title = svgElement("title");
  title.textContent = `${concept.label} · ${concept.document_name} · ${concept.subject_name}`;
  group.appendChild(title);

  const handleHover = (nextHoveredId) => {
    graphUi.hoveredId = nextHoveredId;
    updateGraphFocus(context);
  };

  group.addEventListener("mouseenter", () => handleHover(concept.id));
  group.addEventListener("mouseleave", () => handleHover(null));
  group.addEventListener("focus", () => handleHover(concept.id));
  group.addEventListener("blur", () => handleHover(null));
  group.addEventListener("click", (event) => {
    event.stopPropagation();
    state.selectedConceptId = concept.id;
    state.explanation = null;
    graphUi.hoveredId = concept.id;
    updateGraphFocus(context);
    renderConceptExplanation();
    callGraphAction(handlers.onSelect, concept);
  });
  group.addEventListener("keydown", (event) => {
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      state.selectedConceptId = concept.id;
      state.explanation = null;
      graphUi.hoveredId = concept.id;
      updateGraphFocus(context);
      renderConceptExplanation();
      callGraphAction(handlers.onSelect, concept);
    }
  });

  root.appendChild(group);
  graphUi.nodeElements.set(concept.id, group);
}

export function renderGraphControls() {
  const subjectSelect = document.getElementById("graphSubjectSelect");
  const documentSelect = document.getElementById("graphDocumentSelect");
  const subjects = state.workspace.subjects || [];

  subjectSelect.innerHTML = `
    <option value="">All Subjects</option>
    ${subjects.map((subject) => `
        <option value="${escapeHtml(subject.subject_name)}" ${subject.subject_name === state.graphFilters.subjectName ? "selected" : ""}>
          ${escapeHtml(subject.subject_name)} (${subject.document_count})
        </option>
      `).join("")}
  `;

  const docs = graphDocuments();
  documentSelect.innerHTML = `
    <option value="">All Documents</option>
    ${docs.map((docItem) => `
        <option value="${escapeHtml(docItem.id)}" ${docItem.id === state.graphFilters.docId ? "selected" : ""}>
          ${escapeHtml(docItem.filename)}
        </option>
      `).join("")}
  `;
}

export function renderConceptMap(handlers = {}) {
  const svg = document.getElementById("conceptMap");
  svg.innerHTML = "";
  svg.setAttribute("viewBox", `0 0 ${VIEWBOX.width} ${VIEWBOX.height}`);
  renderGraphControls();

  graphUi.callbacks = handlers;
  graphUi.context = buildGraphContext();
  graphUi.nodeElements = new Map();
  graphUi.edgeElements = [];
  bindStageInteractions();

  const signature = graphSignature();
  const signatureChanged = graphUi.signature !== signature;
  if (signatureChanged) {
    graphUi.signature = signature;
    graphUi.hoveredId = null;
  }

  if (!state.graph.nodes.length) {
    fitViewport();
    const empty = svgElement("text", {
      x: VIEWBOX.width / 2,
      y: VIEWBOX.height / 2,
      "text-anchor": "middle",
      class: "graph-empty-state"
    });
    empty.textContent = "No concepts available for this filter yet.";
    svg.appendChild(empty);
    updateHovercard(graphUi.context);
    updateSelectionBar(graphUi.context);
    updateConceptMetaChips(graphUi.context);
    return;
  }

  const defs = svgElement("defs");
  const gradient = svgElement("linearGradient", {
    id: "graphProgressGradient",
    x1: "0%",
    y1: "0%",
    x2: "100%",
    y2: "0%"
  });
  gradient.appendChild(svgElement("stop", { offset: "0%", "stop-color": "#0f766e" }));
  gradient.appendChild(svgElement("stop", { offset: "100%", "stop-color": "#d97706" }));
  defs.appendChild(gradient);
  svg.appendChild(defs);

  const viewportGroup = svgElement("g", { id: "graphViewportGroup" });
  const edgeLayer = svgElement("g", { class: "graph-edge-layer" });
  const nodeLayer = svgElement("g", { class: "graph-node-layer" });
  viewportGroup.appendChild(edgeLayer);
  viewportGroup.appendChild(nodeLayer);
  svg.appendChild(viewportGroup);
  graphUi.viewportGroup = viewportGroup;

  state.graph.edges.forEach((edge, index) => {
    const edgeGroup = svgElement("g", { class: "graph-edge-group" });
    renderEdge(edge, index, graphUi.context, edgeGroup);
    edgeLayer.appendChild(edgeGroup);
  });

  graphUi.context.nodes.forEach((concept) => {
    renderNode(concept, graphUi.context, handlers, nodeLayer);
  });

  if (signatureChanged || (graphUi.scale === 1 && graphUi.tx === 0 && graphUi.ty === 0)) {
    fitViewport();
  } else {
    applyViewport();
  }

  updateGraphFocus(graphUi.context);
}

export function renderConceptExplanation() {
  const title = document.getElementById("conceptTitle");
  const explanation = document.getElementById("conceptExplanation");
  const takeaway = document.getElementById("conceptTakeaway");
  const selected = selectedGraphConcept();

  updateConceptMetaChips(graphUi.context || buildGraphContext());

  if (!state.explanation) {
    title.textContent = selected?.label || "Select a concept";
    explanation.textContent = selected?.description
      ? truncate(selected.description, 240)
      : "Click any node in the graph to generate an explanation at the chosen depth.";
    takeaway.textContent = selected
      ? `Key takeaway: ${percentLabel(selected.mastery)} mastery right now. Use Teach This or Review This to strengthen it.`
      : "";
    return;
  }

  title.textContent = state.explanation.concept;
  explanation.textContent = state.explanation.explanation;
  takeaway.textContent = `Key takeaway: ${state.explanation.takeaway}`;

  // Phase 4c: Render concept depth data (claims, examples, misconceptions)
  const depthPanel = document.getElementById("conceptDepthPanel");
  if (depthPanel) {
    const claims = state.explanation.claims || [];
    const examples = state.explanation.examples || [];
    const misconceptions = state.explanation.misconceptions || [];
    const hasDepth = claims.length || examples.length || misconceptions.length;

    if (hasDepth) {
      let html = "";
      if (claims.length) {
        html += `<div class="depth-section"><h4>Key Claims</h4><ul>${claims.map(c =>
          `<li><span class="depth-badge">${escapeHtml(c.claim_type || "fact")}</span> ${escapeHtml(c.claim_text)}</li>`
        ).join("")}</ul></div>`;
      }
      if (examples.length) {
        html += `<div class="depth-section"><h4>Examples</h4><ul>${examples.map(e =>
          `<li><span class="depth-badge">${escapeHtml(e.example_type || "example")}</span> ${escapeHtml(e.example_text)}</li>`
        ).join("")}</ul></div>`;
      }
      if (misconceptions.length) {
        html += `<div class="depth-section"><h4>Misconceptions</h4><ul>${misconceptions.map(m =>
          `<li><strong>${escapeHtml(m.label)}</strong>: ${escapeHtml(m.description)}${m.repair_strategy ? `<br><em>Fix: ${escapeHtml(m.repair_strategy)}</em>` : ""}</li>`
        ).join("")}</ul></div>`;
      }
      depthPanel.innerHTML = html;
      depthPanel.classList.remove("hidden");
    } else {
      depthPanel.innerHTML = "";
      depthPanel.classList.add("hidden");
    }
  }
}

export function renderChatLog() {
  const chatLog = document.getElementById("chatLog");
  if (!chatLog) return;
  chatLog.innerHTML = "";
  state.chat.forEach((message) => {
    const bubble = document.createElement("div");
    bubble.className = `message ${message.role}`;
    bubble.textContent = message.text;
    chatLog.appendChild(bubble);
  });
  chatLog.scrollTop = chatLog.scrollHeight;
}
