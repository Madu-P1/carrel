import { useEffect, useMemo, useState } from "preact/hooks";

import { Card, Icon, Stack, Text } from "@/design-system";
import {
  concepts,
  library,
  type ConceptExplainResponse,
  type ConceptGraphEdge,
  type ConceptGraphNode,
  type ConceptGraphResponse,
  type SubjectSummary,
} from "@/services/api/endpoints";
import { navigateTo } from "@/app/shell/useAppShell";

import styles from "./ConceptGraphView.module.css";

/**
 * Concept graph view.
 *
 * Renders the LLM-extracted concept network as an SVG node-link graph.
 * Backend (`/api/concepts/graph`) does the heavy lifting:
 *   - Returns nodes with pre-computed (x, y) positions from
 *     `services.helpers.concept_positions` — a hand-rolled layout that
 *     clusters concepts by document along an arc. We don't pay for a
 *     client-side force simulation; positions arrive in the response.
 *   - Edge relationships come straight from the extractor's vocabulary
 *     ("supports", "contrasts with", "includes"). The renderer encodes
 *     each as a different stroke style: solid (supports), dashed
 *     (contrasts with), dotted (includes). Communicates relationship at
 *     a glance without a legend.
 *
 * Click a node → fetches `/api/concepts/{id}/explain` for the side
 * panel (claims, examples, misconceptions). The graph itself stays
 * mounted; the panel slides in over the right margin.
 *
 * Filter dropdown: select a subject to scope the graph. Default is
 * "All subjects" → every concept across the library. Subject scope
 * cuts down visual noise for large corpora and reads as a per-subject
 * concept atlas.
 */

interface SelectedConcept {
  id: string;
  data: ConceptExplainResponse | null;
  loading: boolean;
  error: string | null;
}

const PADDING = 80; // viewport breathing room around the node bounding box

export function ConceptGraphView() {
  const [graph, setGraph] = useState<ConceptGraphResponse | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphLoading, setGraphLoading] = useState(true);
  const [subjects, setSubjects] = useState<SubjectSummary[]>([]);
  const [subjectFilter, setSubjectFilter] = useState<string>("");
  const [hoveredNodeId, setHoveredNodeId] = useState<string | null>(null);
  const [selected, setSelected] = useState<SelectedConcept | null>(null);

  // Fetch subjects once on mount for the filter dropdown.
  useEffect(() => {
    library
      .subjects()
      .then((response) => setSubjects(response.subjects))
      .catch(() => {
        // Subject filter is non-critical; graph still loads with "All".
        // Don't surface an error — just leave the dropdown empty.
      });
  }, []);

  // (Re)fetch the graph whenever the subject filter changes.
  useEffect(() => {
    setGraphLoading(true);
    setGraphError(null);
    concepts
      .graph(subjectFilter ? { subjectName: subjectFilter } : {})
      .then((response) => {
        setGraph(response);
      })
      .catch((err) => {
        setGraphError((err as Error).message ?? "Unknown error");
      })
      .finally(() => {
        setGraphLoading(false);
      });
  }, [subjectFilter]);

  // Compute the SVG viewBox from node positions so the graph fills the
  // available canvas regardless of how many nodes there are. Falls back
  // to a sensible default when there are no nodes (shouldn't render
  // anyway in that branch).
  const viewBox = useMemo(() => {
    if (!graph || graph.nodes.length === 0) return "0 0 800 600";
    const xs = graph.nodes.map((n) => n.x);
    const ys = graph.nodes.map((n) => n.y);
    const minX = Math.min(...xs) - PADDING;
    const minY = Math.min(...ys) - PADDING;
    const maxX = Math.max(...xs) + PADDING;
    const maxY = Math.max(...ys) + PADDING;
    return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`;
  }, [graph]);

  const nodesById = useMemo(() => {
    const map = new Map<string, ConceptGraphNode>();
    if (graph) {
      for (const node of graph.nodes) map.set(node.id, node);
    }
    return map;
  }, [graph]);

  const handleNodeClick = (node: ConceptGraphNode) => {
    setSelected({ id: node.id, data: null, loading: true, error: null });
    concepts
      .explain(node.id)
      .then((data) => {
        // Only update if the user hasn't already moved on to another node
        // (preact + closure on `node.id` already guards this).
        setSelected({ id: node.id, data, loading: false, error: null });
      })
      .catch((err) => {
        setSelected({
          id: node.id,
          data: null,
          loading: false,
          error: (err as Error).message ?? "Unknown error",
        });
      });
  };

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>Concept atlas</span>
        <h1 className={styles.heading}>The shape of your library.</h1>
        <Text tone="secondary">
          Concepts the model has extracted across your sources, with the
          relationships it inferred between them. Solid lines support, dashed
          contrast, dotted contain. Click any node to see its claims,
          examples, and known misconceptions.
        </Text>
      </header>

      <div className={styles.toolbar}>
        <label className={styles.filterLabel}>
          <span className={styles.filterLabelText}>Subject</span>
          <select
            className={styles.filterSelect}
            value={subjectFilter}
            onChange={(e) =>
              setSubjectFilter((e.currentTarget as HTMLSelectElement).value)
            }
            aria-label="Filter graph by subject"
          >
            <option value="">All subjects</option>
            {subjects.map((s) => (
              <option key={s.subject_name} value={s.subject_name}>
                {s.subject_name} ({s.source_count})
              </option>
            ))}
          </select>
        </label>
        {graph ? (
          <span className={styles.graphCount}>
            {graph.nodes.length} concept{graph.nodes.length === 1 ? "" : "s"} ·{" "}
            {graph.edges.length} edge{graph.edges.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      <div className={styles.canvasRow}>
        <div className={styles.canvasFrame}>
          {graphError ? (
            <GraphErrorState
              message={graphError}
              onRetry={() => setSubjectFilter((prev) => prev)}
            />
          ) : graphLoading && !graph ? (
            <div className={styles.skeleton} aria-label="Loading concept graph" />
          ) : !graph || graph.nodes.length === 0 ? (
            <GraphEmptyState />
          ) : (
            <svg
              className={styles.graph}
              viewBox={viewBox}
              preserveAspectRatio="xMidYMid meet"
              role="figure"
              aria-label="Concept graph"
            >
              {/* Edges first so they sit BEHIND nodes. SVG paints in document
                  order and there's no z-index in pure SVG without groups. */}
              <g className={styles.edgeLayer} aria-hidden>
                {graph.edges.map((edge) => (
                  <Edge
                    key={`${edge.source}-${edge.target}`}
                    edge={edge}
                    nodesById={nodesById}
                    dimmed={
                      hoveredNodeId !== null &&
                      edge.source !== hoveredNodeId &&
                      edge.target !== hoveredNodeId
                    }
                  />
                ))}
              </g>
              <g className={styles.nodeLayer}>
                {graph.nodes.map((node) => (
                  <Node
                    key={node.id}
                    node={node}
                    isSelected={selected?.id === node.id}
                    isHovered={hoveredNodeId === node.id}
                    isDimmed={
                      hoveredNodeId !== null && hoveredNodeId !== node.id
                    }
                    onClick={() => handleNodeClick(node)}
                    onHover={(id) => setHoveredNodeId(id)}
                  />
                ))}
              </g>
            </svg>
          )}
        </div>

        {selected ? (
          <ConceptDetailPanel
            selected={selected}
            onClose={() => setSelected(null)}
            onOpenInReader={(node) => {
              if (!node) return;
              navigateTo(`/reader/${encodeURIComponent(node.document_id)}`);
            }}
            sourceNode={nodesById.get(selected.id) ?? null}
          />
        ) : null}
      </div>
    </div>
  );
}

interface NodeProps {
  node: ConceptGraphNode;
  isSelected: boolean;
  isHovered: boolean;
  isDimmed: boolean;
  onClick: () => void;
  onHover: (id: string | null) => void;
}

function Node({
  node,
  isSelected,
  isHovered,
  isDimmed,
  onClick,
  onHover,
}: NodeProps) {
  // Mastery is a 0-1 float in the schema. Surface it as fill opacity so
  // weak concepts read pale and strong concepts read full-strength. When
  // mastery is 0 (the common case for a fresh ingest) we fall back to
  // 0.45 so the node is still visible.
  const mastery = node.mastery > 0 ? node.mastery : 0.45;
  const radius = isHovered || isSelected ? 10 : 8;

  // Truncate label to ~20 chars with ellipsis so long concept names
  // don't crash into adjacent nodes. Hovered nodes get the full label.
  const visibleLabel =
    isHovered || isSelected || node.label.length <= 20
      ? node.label
      : `${node.label.slice(0, 18)}…`;

  return (
    <g
      className={[
        styles.node,
        isSelected ? styles.nodeSelected : "",
        isHovered ? styles.nodeHovered : "",
        isDimmed ? styles.nodeDimmed : "",
      ]
        .filter(Boolean)
        .join(" ")}
      transform={`translate(${node.x} ${node.y})`}
      onClick={onClick}
      onMouseEnter={() => onHover(node.id)}
      onMouseLeave={() => onHover(null)}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onClick();
        }
      }}
      aria-label={`${node.label} concept`}
    >
      <circle r={radius} className={styles.nodeCircle} fillOpacity={mastery} />
      <text className={styles.nodeLabel} dy={radius + 14}>
        {visibleLabel}
      </text>
    </g>
  );
}

interface EdgeProps {
  edge: ConceptGraphEdge;
  nodesById: Map<string, ConceptGraphNode>;
  dimmed: boolean;
}

function Edge({ edge, nodesById, dimmed }: EdgeProps) {
  const source = nodesById.get(edge.source);
  const target = nodesById.get(edge.target);
  if (!source || !target) return null;

  // Encode relationship as stroke style so it reads at a glance
  // without a legend: solid for support, dashed for contrast, dotted
  // for inclusion. Anything else falls through to solid.
  let dashArray: string | undefined;
  if (edge.relationship === "contrasts with") dashArray = "4 4";
  else if (edge.relationship === "includes") dashArray = "1 5";

  return (
    <line
      className={[styles.edge, dimmed ? styles.edgeDimmed : ""]
        .filter(Boolean)
        .join(" ")}
      x1={source.x}
      y1={source.y}
      x2={target.x}
      y2={target.y}
      strokeDasharray={dashArray}
    />
  );
}

interface ConceptDetailPanelProps {
  selected: SelectedConcept;
  sourceNode: ConceptGraphNode | null;
  onClose: () => void;
  onOpenInReader: (node: ConceptGraphNode | null) => void;
}

function ConceptDetailPanel({
  selected,
  sourceNode,
  onClose,
  onOpenInReader,
}: ConceptDetailPanelProps) {
  const labelFromNode = sourceNode?.label ?? "Concept";
  return (
    <aside className={styles.detailPanel} aria-label="Concept detail">
      <div className={styles.detailHeader}>
        <span className={styles.eyebrow}>Concept</span>
        <button
          type="button"
          className={styles.detailClose}
          onClick={onClose}
          aria-label="Close concept detail"
        >
          <Icon name="x" size={14} />
        </button>
      </div>
      <h2 className={styles.detailTitle}>
        {selected.data?.concept ?? labelFromNode}
      </h2>
      {sourceNode ? (
        <div className={styles.detailMeta}>
          <span>{sourceNode.document_name ?? "Source"}</span>
          {sourceNode.subject_name ? (
            <>
              <span aria-hidden> · </span>
              <span>{sourceNode.subject_name}</span>
            </>
          ) : null}
        </div>
      ) : null}

      {selected.loading ? (
        <Text tone="secondary">Loading the concept's notes…</Text>
      ) : selected.error ? (
        <Text tone="secondary">Couldn't load this concept: {selected.error}</Text>
      ) : selected.data ? (
        <Stack gap={4}>
          {selected.data.takeaway ? (
            <div className={styles.detailSection}>
              <span className={styles.detailLabel}>Takeaway</span>
              <Text>{selected.data.takeaway}</Text>
            </div>
          ) : null}

          {selected.data.claims.length > 0 ? (
            <div className={styles.detailSection}>
              <span className={styles.detailLabel}>Claims</span>
              <ul className={styles.detailList}>
                {selected.data.claims.map((c) => (
                  <li key={c.id}>{c.claim_text}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {selected.data.examples.length > 0 ? (
            <div className={styles.detailSection}>
              <span className={styles.detailLabel}>Examples</span>
              <ul className={styles.detailList}>
                {selected.data.examples.map((e) => (
                  <li key={e.id}>{e.example_text}</li>
                ))}
              </ul>
            </div>
          ) : null}

          {selected.data.misconceptions.length > 0 ? (
            <div className={styles.detailSection}>
              <span className={styles.detailLabel}>Misconceptions</span>
              <ul className={styles.detailList}>
                {selected.data.misconceptions.map((m) => (
                  <li key={m.id}>
                    <strong>{m.label}.</strong>{" "}
                    {m.description ?? ""}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {sourceNode ? (
            <button
              type="button"
              className={styles.detailOpenButton}
              onClick={() => onOpenInReader(sourceNode)}
            >
              Open the source in the Reader
              <Icon name="arrow-right" size={14} />
            </button>
          ) : null}
        </Stack>
      ) : null}
    </aside>
  );
}

function GraphEmptyState() {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <span className={styles.stateEyebrow}>No concepts yet</span>
        <Text as="h2" className={styles.stateHeading}>
          Nothing to plot.
        </Text>
        <Text tone="secondary">
          Import a source in Library and the model will extract concepts on
          ingest. They appear here once the extractor finishes the pass.
        </Text>
      </Stack>
    </Card>
  );
}

function GraphErrorState({
  message,
  onRetry,
}: {
  message: string;
  onRetry: () => void;
}) {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <span className={styles.stateEyebrow}>Graph unavailable</span>
        <Text as="h2" className={styles.stateHeading}>
          Couldn't load the concept graph.
        </Text>
        <Text tone="secondary">{message}</Text>
        <div>
          <button
            type="button"
            className={styles.detailOpenButton}
            onClick={onRetry}
          >
            Reload the graph
          </button>
        </div>
      </Stack>
    </Card>
  );
}
