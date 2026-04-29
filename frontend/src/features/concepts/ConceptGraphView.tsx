import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Card, Stack, Text } from "@/design-system";
import {
  concepts,
  library,
  type ConceptExplainResponse,
  type ConceptGraphResponse,
  type SubjectSummary,
} from "@/services/api/endpoints";
import { navigateTo } from "@/app/shell/useAppShell";

import styles from "./ConceptGraphView.module.css";

/**
 * Concept graph — 3D force-directed atlas.
 *
 * Implements the design spec at `~/Downloads/Einstein Design System (1)/
 * Concepts View.html`: full-bleed 3D force graph with subject-coloured
 * nodes, slide-in detail panel, hover card, legend, filter pills,
 * starfield, selection point-light + directional particles.
 *
 * The previous SVG implementation was a "trace the bones" pass using
 * server-pre-computed 2D positions. That was useful as an MVP but the
 * spec wants a real 3D atlas — so this rewrite drops the 2D layout and
 * lets `3d-force-graph` (with three.js) compute the 3D physics in the
 * browser. Backend `(x, y)` positions are ignored; we only need the
 * relational shape (nodes + edges + subject + mastery).
 *
 * Bundle cost: three.js + 3d-force-graph total ~700kB minified (~210kB
 * gzipped). To keep the entry chunk lean, both libs are loaded via
 * `await import(...)` inside an effect so they only land when the
 * /concepts route mounts. The build script's chunk-base rewrite
 * (`__carrelAssetBase`) handles the dynamic-import path under file://.
 */

type ForceGraph3DInstance = {
  graphData(data: { nodes: GraphNode[]; links: GraphLink[] }): ForceGraph3DInstance;
  graphData(): { nodes: GraphNode[]; links: GraphLink[] };
  backgroundColor(c: string): ForceGraph3DInstance;
  showNavInfo(b: boolean): ForceGraph3DInstance;
  nodeId(k: string): ForceGraph3DInstance;
  nodeLabel(fn: () => string): ForceGraph3DInstance;
  nodeColor(fn: (n: GraphNode) => string): ForceGraph3DInstance;
  nodeColor(): (n: GraphNode) => string;
  nodeVal(fn: (n: GraphNode) => number): ForceGraph3DInstance;
  nodeOpacity(n: number): ForceGraph3DInstance;
  nodeResolution(n: number): ForceGraph3DInstance;
  linkColor(fn: (l: GraphLink) => string): ForceGraph3DInstance;
  linkColor(): (l: GraphLink) => string;
  linkWidth(fn: (l: GraphLink) => number): ForceGraph3DInstance;
  linkWidth(): (l: GraphLink) => number;
  linkOpacity(n: number): ForceGraph3DInstance;
  linkDirectionalParticles(fn: (l: GraphLink) => number): ForceGraph3DInstance;
  linkDirectionalParticles(): (l: GraphLink) => number;
  linkDirectionalParticleWidth(n: number): ForceGraph3DInstance;
  linkDirectionalParticleColor(fn: () => string): ForceGraph3DInstance;
  linkDirectionalParticleSpeed(n: number): ForceGraph3DInstance;
  onNodeClick(fn: (n: GraphNode | null, e?: MouseEvent) => void): ForceGraph3DInstance;
  onNodeHover(fn: (n: GraphNode | null) => void): ForceGraph3DInstance;
  onBackgroundClick(fn: () => void): ForceGraph3DInstance;
  cameraPosition(): { x: number; y: number; z: number };
  cameraPosition(
    pos: { x: number; y: number; z: number },
    look?: { x: number; y: number; z: number },
    transitionMs?: number
  ): ForceGraph3DInstance;
  zoomToFit(durationMs?: number, padding?: number): ForceGraph3DInstance;
  scene(): unknown;
  width(n: number): ForceGraph3DInstance;
  height(n: number): ForceGraph3DInstance;
  _destructor?: () => void;
};

interface GraphNode {
  id: string;
  label: string;
  subject: string;
  weight: number;
  mastery: number;
  document_id: string;
  document_name: string | null;
  // 3d-force-graph fills these during simulation
  x?: number;
  y?: number;
  z?: number;
}

interface GraphLink {
  source: string | GraphNode;
  target: string | GraphNode;
  relationship: string;
}

/**
 * Subject → colour mapping. Spec lists Finance (teal), Tax (amber), Law
 * (purple). For other subjects (Stats, Bio, etc.) we deterministically
 * pick from a small set of mid-saturation hues so colours are stable
 * across reloads — same subject always reads the same colour.
 *
 * Each entry has CSS rgb (used for tags + nodes), hex int (for three.js
 * lights/materials), and a CSS class for the tag pill in the panel.
 */
const SUBJECT_PALETTE: Record<string, { css: string; hex: number; tag: string }> = {
  Finance: { css: "rgb(87, 214, 195)", hex: 0x57d6c3, tag: "tagFinance" },
  Tax: { css: "rgb(200, 155, 40)", hex: 0xc89b28, tag: "tagTax" },
  Law: { css: "rgb(155, 120, 210)", hex: 0x9b78d2, tag: "tagLaw" },
  Stats: { css: "rgb(232, 138, 138)", hex: 0xe88a8a, tag: "tagOther" },
  Biology: { css: "rgb(130, 200, 140)", hex: 0x82c88c, tag: "tagOther" },
  General: { css: "rgb(140, 175, 230)", hex: 0x8cafe6, tag: "tagOther" },
  Other: { css: "rgb(180, 180, 200)", hex: 0xb4b4c8, tag: "tagOther" },
};
// Backup palette for any subject not pinned in SUBJECT_PALETTE. Picked
// deterministically by hashing the subject name into the array index so
// each subject always reads the same colour across reloads.
const PALETTE_BACKUP: Array<{ css: string; hex: number; tag: string }> = [
  { css: "rgb(140, 200, 230)", hex: 0x8cc8e6, tag: "tagOther" },
  { css: "rgb(220, 170, 110)", hex: 0xdcaa6e, tag: "tagOther" },
  { css: "rgb(190, 160, 230)", hex: 0xbea0e6, tag: "tagOther" },
  { css: "rgb(150, 220, 180)", hex: 0x96dcb4, tag: "tagOther" },
];
const FALLBACK_SUBJECT = SUBJECT_PALETTE.Other;

function _hashSubject(name: string): number {
  let h = 0;
  for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) | 0;
  return Math.abs(h);
}

function paletteFor(subject: string | null | undefined) {
  if (!subject) return FALLBACK_SUBJECT;
  const pinned = SUBJECT_PALETTE[subject];
  if (pinned) return pinned;
  return PALETTE_BACKUP[_hashSubject(subject) % PALETTE_BACKUP.length];
}

interface SelectedConcept {
  id: string;
  data: ConceptExplainResponse | null;
  loading: boolean;
  error: string | null;
}

export function ConceptGraphView() {
  const [graph, setGraph] = useState<ConceptGraphResponse | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [graphLoading, setGraphLoading] = useState(true);
  // `subjects` is fetched but not currently displayed in this view —
  // the filter pills derive their list from concepts present in the
  // graph (subjectsInGraph below) so we only show pills for subjects
  // that actually have nodes. Keeping the fetch in case a future pass
  // wants to surface "subjects with concepts vs without" as a hint.
  const [, setSubjects] = useState<SubjectSummary[]>([]);
  const [filter, setFilter] = useState<string>("All");
  const [selected, setSelected] = useState<SelectedConcept | null>(null);
  const [hoverInfo, setHoverInfo] = useState<{
    label: string;
    subject: string;
    weight: number;
    x: number;
    y: number;
  } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const graphRef = useRef<ForceGraph3DInstance | null>(null);
  const selectionRef = useRef<{
    selectedId: string | null;
    highlightedNodes: Set<string>;
    highlightedLinks: Set<GraphLink>;
    pointLight: { intensity: number; position: { set: (x: number, y: number, z: number) => void } } | null;
  }>({ selectedId: null, highlightedNodes: new Set(), highlightedLinks: new Set(), pointLight: null });

  // Fetch concepts and subjects.
  useEffect(() => {
    library
      .subjects()
      .then((response) => setSubjects(response.subjects))
      .catch(() => {
        // Subject filter falls back to "All" if subjects can't load.
      });
  }, []);

  useEffect(() => {
    setGraphLoading(true);
    setGraphError(null);
    concepts
      .graph(filter !== "All" ? { subjectName: filter } : {})
      .then((response) => {
        setGraph(response);
        // Populate the concept-id → document_id side-channel map so the
        // detail panel's "Open in Reader" button can navigate without
        // an extra round-trip to /api/documents.
        conceptDocIdMap.clear();
        for (const node of response.nodes) {
          conceptDocIdMap.set(node.id, node.document_id);
        }
      })
      .catch((err) => {
        setGraphError((err as Error).message ?? "Unknown error");
      })
      .finally(() => {
        setGraphLoading(false);
      });
  }, [filter]);

  // Build the GraphNode/GraphLink arrays for 3d-force-graph.
  const graphData = useMemo(() => {
    if (!graph) return null;
    // Compute connection count (weight) per node from edge incidences.
    const degree = new Map<string, number>();
    for (const edge of graph.edges) {
      degree.set(edge.source, (degree.get(edge.source) ?? 0) + 1);
      degree.set(edge.target, (degree.get(edge.target) ?? 0) + 1);
    }
    const nodes: GraphNode[] = graph.nodes.map((n) => ({
      id: n.id,
      label: n.label,
      subject: n.subject_name ?? "Other",
      // Clamp weight to a small range so a hub concept doesn't render
      // as a huge ball that visually dominates the cloud. The spec
      // sized nodes 4..9; we map degree count into the same band so a
      // single highly-connected node reads as "more important", not
      // "the only thing on screen". `nodeVal` below applies the
      // pow(weight, 1.6) curve on top of this clamped input.
      weight: Math.min(9, Math.max(2, Math.ceil(Math.sqrt((degree.get(n.id) ?? 1) * 4)))),
      mastery: n.mastery,
      document_id: n.document_id,
      document_name: n.document_name,
    }));
    const links: GraphLink[] = graph.edges.map((e) => ({
      source: e.source,
      target: e.target,
      relationship: e.relationship,
    }));
    return { nodes, links };
  }, [graph]);

  const subjectsInGraph = useMemo(() => {
    if (!graph) return [];
    const set = new Set<string>();
    for (const n of graph.nodes) {
      if (n.subject_name) set.add(n.subject_name);
    }
    return [...set].sort();
  }, [graph]);

  // Initialise the 3D force graph once `graphData` is available.
  // Lazy-import three.js + 3d-force-graph so they don't bloat the entry
  // chunk. Vite code-splits the dynamic imports automatically.
  useEffect(() => {
    if (!graphData || !containerRef.current) return;

    let cancelled = false;
    let graphInstance: ForceGraph3DInstance | null = null;
    let resizeObserver: ResizeObserver | null = null;

    (async () => {
      const [{ default: ForceGraph3D }, three] = await Promise.all([
        import("3d-force-graph"),
        import("three"),
      ]);
      if (cancelled || !containerRef.current) return;
      const THREE = three;

      // Reset the container in case we're remounting (filter change).
      const container = containerRef.current;
      container.innerHTML = "";

      // 3d-force-graph 1.80 changed the construction API — was a curried
      // function, now a constructor: `new ForceGraph3D(element, opts)`.
      // Cast through `unknown` to our local interface since the library's
      // generics chain doesn't quite line up with our explicit method
      // signatures (the runtime behavior is identical).
      //
      // controlType: 'orbit' is more familiar than the default trackball
      // for users who don't know 3D editors. Drag = orbit around centre,
      // scroll = zoom (camera distance from look-at point), right-click
      // drag = pan. Trackball would also rotate the up-axis on diagonal
      // drags, which makes a graph feel disorientating.
      graphInstance = new ForceGraph3D(container, {
        controlType: "orbit",
        rendererConfig: { antialias: true, alpha: true },
      }) as unknown as ForceGraph3DInstance;
      graphRef.current = graphInstance;

      const sel = selectionRef.current;
      sel.selectedId = null;
      sel.highlightedNodes = new Set();
      sel.highlightedLinks = new Set();

      const nodeColorFn = (n: GraphNode) => {
        const base = paletteFor(n.subject).css;
        if (!sel.selectedId) return base;
        if (n.id === sel.selectedId) return base;
        if (sel.highlightedNodes.has(n.id)) return base;
        return "rgba(255,255,255,0.15)";
      };
      const linkColorFn = (l: GraphLink) => {
        if (sel.highlightedLinks.has(l)) return "rgba(87,214,195,0.85)";
        // Idle edges: brighter than the previous 0.10 so the network
        // shape reads at a glance. The selection mode dims to 0.05 so
        // the highlighted path still pops.
        if (sel.selectedId) return "rgba(255,255,255,0.05)";
        return "rgba(255,255,255,0.22)";
      };
      const linkWidthFn = (l: GraphLink) => (sel.highlightedLinks.has(l) ? 2 : 0.8);
      const linkParticlesFn = (l: GraphLink) => (sel.highlightedLinks.has(l) ? 4 : 0);

      const instanceWithEngine = graphInstance as unknown as {
        d3Force(name: string, fn?: unknown): unknown;
        cooldownTicks(n: number): unknown;
        onEngineStop(fn: () => void): unknown;
      };

      graphInstance
        .backgroundColor("rgba(0,0,0,0)")
        .showNavInfo(false)
        .nodeId("id")
        .nodeLabel(() => "")
        .nodeColor(nodeColorFn)
        // Slightly flatter exponent than the previous pow(weight, 1.6)
        // so hub nodes are bigger but not 3× their neighbours. Floor at
        // ~6 so even a degree-1 node has a clickable target on screen.
        .nodeVal((n: GraphNode) => 6 + Math.pow(n.weight, 1.4))
        .nodeOpacity(0.95)
        .nodeResolution(20)
        .linkColor(linkColorFn)
        .linkWidth(linkWidthFn)
        .linkOpacity(0.85)
        .linkDirectionalParticles(linkParticlesFn)
        .linkDirectionalParticleWidth(1.8)
        .linkDirectionalParticleColor(() => "rgb(87,214,195)")
        .linkDirectionalParticleSpeed(0.004)
        .onNodeClick((n) => handleNodeSelect(n))
        .onNodeHover((n) => handleNodeHover(n))
        .onBackgroundClick(() => handleClearSelection())
        .graphData(graphData);

      // Tune the d3-force simulation. Defaults assume a denser graph
      // than ours (43 nodes / 27 edges has many isolated stubs); the
      // result reads as scattered specks. Tighten so:
      //   - nodes repel each other more weakly (charge strength less
      //     negative) — they settle closer together.
      //   - linked nodes pull in tighter (smaller link distance).
      // Also cap the simulation at 240 ticks so it stops running
      // perpetually (defaults to 15000, which holds the CPU forever
      // on weak graphs that never converge).
      const chargeForce = instanceWithEngine.d3Force("charge") as
        | { strength: (s: number) => unknown }
        | undefined;
      if (chargeForce && typeof chargeForce.strength === "function") {
        chargeForce.strength(-180);
      }
      const linkForce = instanceWithEngine.d3Force("link") as
        | { distance: (n: number) => unknown }
        | undefined;
      if (linkForce && typeof linkForce.distance === "function") {
        linkForce.distance(45);
      }
      instanceWithEngine.cooldownTicks(240);

      // After the simulation settles, frame every node in view so the
      // user sees the whole atlas on first paint. Otherwise the camera
      // sits at the library's default position and the cluster ends up
      // off-centre / clipped (the original screenshot you flagged).
      instanceWithEngine.onEngineStop(() => {
        if (!cancelled && graphInstance) {
          graphInstance.zoomToFit(800, 80);
        }
      });

      // Match the canvas to the container size + watch for resizes.
      const fit = () => {
        if (!graphInstance || !containerRef.current) return;
        const { clientWidth: w, clientHeight: h } = containerRef.current;
        graphInstance.width(w).height(h);
      };
      fit();
      resizeObserver = new ResizeObserver(fit);
      resizeObserver.observe(container);

      // ── Scene enhancements (lights + starfield) ──
      const scene = graphInstance.scene() as {
        add: (obj: unknown) => void;
      };
      const ambient = new THREE.AmbientLight(0x223355, 0.6);
      scene.add(ambient);
      const fillLight = new THREE.DirectionalLight(0x4488cc, 0.4);
      fillLight.position.set(1, 1, 2);
      scene.add(fillLight);

      // Selection point-light pulses around the selected node.
      const selLight = new THREE.PointLight(0x57d6c3, 0, 80);
      scene.add(selLight);
      sel.pointLight = selLight as unknown as typeof sel.pointLight;

      // Starfield (the spec calls for a sphere of points around the
      // graph at radius 600..1000 — feels like a study lamp at midnight).
      const starPositions: number[] = [];
      for (let i = 0; i < 3000; i++) {
        const theta = Math.random() * Math.PI * 2;
        const phi = Math.acos(2 * Math.random() - 1);
        const r = 600 + Math.random() * 400;
        starPositions.push(
          r * Math.sin(phi) * Math.cos(theta),
          r * Math.sin(phi) * Math.sin(theta),
          r * Math.cos(phi)
        );
      }
      const starGeo = new THREE.BufferGeometry();
      starGeo.setAttribute(
        "position",
        new THREE.Float32BufferAttribute(starPositions, 3)
      );
      const starMat = new THREE.PointsMaterial({
        color: 0xffffff,
        size: 1.2,
        transparent: true,
        opacity: 0.35,
      });
      scene.add(new THREE.Points(starGeo, starMat));

      // Pulse the selection light. 3d-force-graph 1.80 dropped the
      // `onRenderFramePre` hook (it was on 1.73 — the spec HTML uses it
      // because it's fixed to a CDN copy), so we run our own
      // requestAnimationFrame loop. The loop self-cancels on unmount via
      // the captured `cancelled` flag.
      const pulseLoop = () => {
        if (cancelled) return;
        if (sel.selectedId && sel.pointLight) {
          const t = Date.now() / 1200;
          (sel.pointLight as unknown as { intensity: number }).intensity =
            2.5 + Math.sin(t) * 0.8;
        }
        requestAnimationFrame(pulseLoop);
      };
      requestAnimationFrame(pulseLoop);
    })();

    function handleNodeSelect(node: GraphNode | null) {
      if (!node) {
        handleClearSelection();
        return;
      }
      const sel = selectionRef.current;
      sel.selectedId = node.id;
      sel.highlightedNodes = new Set([node.id]);
      sel.highlightedLinks = new Set();

      const data = graphInstance?.graphData();
      if (data) {
        for (const link of data.links) {
          const srcId = typeof link.source === "object" ? link.source.id : link.source;
          const tgtId = typeof link.target === "object" ? link.target.id : link.target;
          if (srcId === node.id || tgtId === node.id) {
            sel.highlightedLinks.add(link);
            sel.highlightedNodes.add(srcId);
            sel.highlightedNodes.add(tgtId);
          }
        }
      }
      // Trigger re-render of node/link styles by re-applying the
      // accessors. 3d-force-graph re-pulls colours per node/link on the
      // next frame after this call.
      if (graphInstance) {
        graphInstance
          .nodeColor(graphInstance.nodeColor())
          .linkColor(graphInstance.linkColor())
          .linkWidth(graphInstance.linkWidth())
          .linkDirectionalParticles(graphInstance.linkDirectionalParticles());
      }

      // Camera fly-to.
      if (graphInstance && typeof node.x === "number") {
        const dist = 90;
        const nx = node.x ?? 0;
        const ny = node.y ?? 0;
        const nz = node.z ?? 0;
        const mag = Math.hypot(nx, ny, nz) || 1;
        graphInstance.cameraPosition(
          {
            x: nx * (1 + dist / mag),
            y: ny * (1 + dist / mag),
            z: nz * (1 + dist / mag),
          },
          { x: nx, y: ny, z: nz },
          900
        );
        // Move the selection point-light to the node.
        if (sel.pointLight) {
          (sel.pointLight as unknown as {
            position: { set: (x: number, y: number, z: number) => void };
            intensity: number;
          }).position.set(nx, ny, nz);
          (sel.pointLight as unknown as { intensity: number }).intensity = 2.5;
        }
      }

      // Open the detail panel + fetch the explain payload.
      setSelected({ id: node.id, data: null, loading: true, error: null });
      concepts
        .explain(node.id)
        .then((data) => setSelected({ id: node.id, data, loading: false, error: null }))
        .catch((err) =>
          setSelected({
            id: node.id,
            data: null,
            loading: false,
            error: (err as Error).message ?? "Unknown error",
          })
        );
    }

    function handleClearSelection() {
      const sel = selectionRef.current;
      sel.selectedId = null;
      sel.highlightedNodes = new Set();
      sel.highlightedLinks = new Set();
      if (sel.pointLight) {
        (sel.pointLight as unknown as { intensity: number }).intensity = 0;
      }
      if (graphInstance) {
        graphInstance
          .nodeColor(graphInstance.nodeColor())
          .linkColor(graphInstance.linkColor())
          .linkWidth(graphInstance.linkWidth())
          .linkDirectionalParticles(graphInstance.linkDirectionalParticles());
      }
      setSelected(null);
    }

    function handleNodeHover(node: GraphNode | null) {
      if (!node) {
        setHoverInfo(null);
        return;
      }
      setHoverInfo({
        label: node.label,
        subject: node.subject,
        weight: node.weight,
        x: 0,
        y: 0,
      });
    }

    return () => {
      cancelled = true;
      if (resizeObserver) resizeObserver.disconnect();
      if (graphInstance && typeof graphInstance._destructor === "function") {
        graphInstance._destructor();
      }
      graphRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graphData]);

  // Track mouse position for the hover card.
  const [pointer, setPointer] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const onMove = (e: MouseEvent) => {
      const rect = el.getBoundingClientRect();
      setPointer({ x: e.clientX - rect.left + 14, y: e.clientY - rect.top - 40 });
    };
    el.addEventListener("mousemove", onMove, { passive: true });
    return () => el.removeEventListener("mousemove", onMove);
  }, []);

  return (
    <div className={styles.wrap}>
      <header className={styles.header}>
        <span className={styles.eyebrow}>Concept atlas</span>
        <h1 className={styles.heading}>The shape of your library.</h1>
        <Text tone="secondary">
          A 3D map of the concepts the model has extracted from your sources.
          Drag to orbit, scroll to zoom, click any node to see its claims and
          open the source.
        </Text>
      </header>

      <div className={styles.toolbar}>
        <div className={styles.filterPills} role="tablist" aria-label="Subject filter">
          <FilterPill
            label="All subjects"
            active={filter === "All"}
            onClick={() => setFilter("All")}
          />
          {subjectsInGraph.map((s) => (
            <FilterPill
              key={s}
              label={s}
              active={filter === s}
              accent={paletteFor(s).css}
              onClick={() => setFilter(s)}
            />
          ))}
        </div>
        {graph ? (
          <span className={styles.graphCount}>
            {graph.nodes.length} concept{graph.nodes.length === 1 ? "" : "s"} ·{" "}
            {graph.edges.length} edge{graph.edges.length === 1 ? "" : "s"}
          </span>
        ) : null}
      </div>

      <div className={[styles.canvasRow, selected ? styles.canvasRowWithPanel : ""].filter(Boolean).join(" ")}>
        <div className={styles.canvasFrame}>
          {graphError ? (
            <ErrorState
              message={graphError}
              onRetry={() => setFilter((prev) => prev)}
            />
          ) : graphLoading && !graphData ? (
            <div className={styles.skeleton} aria-label="Loading concept graph" />
          ) : !graphData || graphData.nodes.length === 0 ? (
            <EmptyState />
          ) : (
            <>
              <div ref={containerRef} className={styles.canvas} role="figure" aria-label="3D concept graph" />
              <Legend subjects={subjectsInGraph} />
              <ZoomControls graphRef={graphRef} />
              {hoverInfo ? (
                <div
                  className={styles.hoverCard}
                  style={{ transform: `translate(${pointer.x}px, ${pointer.y}px)` }}
                  aria-hidden
                >
                  <div className={styles.hoverLabel}>{hoverInfo.label}</div>
                  <div
                    className={styles.hoverSubject}
                    style={{ color: paletteFor(hoverInfo.subject).css }}
                  >
                    {hoverInfo.subject} · {hoverInfo.weight} connection
                    {hoverInfo.weight === 1 ? "" : "s"}
                  </div>
                </div>
              ) : null}
            </>
          )}
        </div>

        <DetailPanel
          selected={selected}
          onClose={() => {
            setSelected(null);
            if (graphRef.current) {
              const sel = selectionRef.current;
              sel.selectedId = null;
              sel.highlightedNodes.clear();
              sel.highlightedLinks.clear();
              if (sel.pointLight) {
                (sel.pointLight as unknown as { intensity: number }).intensity = 0;
              }
              graphRef.current
                .nodeColor(graphRef.current.nodeColor())
                .linkColor(graphRef.current.linkColor())
                .linkWidth(graphRef.current.linkWidth())
                .linkDirectionalParticles(graphRef.current.linkDirectionalParticles());
            }
          }}
          onOpenInReader={(docId) => navigateTo(`/reader/${encodeURIComponent(docId)}`)}
        />
      </div>
    </div>
  );
}

interface FilterPillProps {
  label: string;
  active: boolean;
  accent?: string;
  onClick: () => void;
}

function FilterPill({ label, active, accent, onClick }: FilterPillProps) {
  return (
    <button
      type="button"
      className={[styles.filterPill, active ? styles.filterPillActive : ""]
        .filter(Boolean)
        .join(" ")}
      style={accent && active ? { color: accent, borderColor: accent } : undefined}
      onClick={onClick}
      role="tab"
      aria-selected={active}
    >
      {label}
    </button>
  );
}

/**
 * Zoom controls — small floating cluster at the bottom-right of the
 * canvas. Three buttons: zoom in, zoom out, fit-all. Each operates on
 * the live graphInstance (passed via ref) and animates the camera move
 * over 320ms so the change reads as deliberate, not a jump cut.
 *
 * Zoom math: scale the camera's distance from origin by 0.78 (in) /
 * 1.28 (out). The graph's force layout centres on the origin, so scaling
 * the camera distance is equivalent to changing the field-of-view
 * without messing with FOV (which has clamping issues in three.js
 * perspective cameras and feels jarring).
 *
 * Fit-all calls 3d-force-graph's built-in zoomToFit which frames every
 * node in view with 60px padding — useful escape hatch when the user
 * gets lost orbiting.
 */
function ZoomControls({
  graphRef,
}: {
  graphRef: { current: ForceGraph3DInstance | null };
}) {
  const transition = 320;

  const scaleCamera = (factor: number) => {
    const g = graphRef.current;
    if (!g) return;
    const pos = g.cameraPosition();
    if (!pos) return;
    g.cameraPosition(
      { x: pos.x * factor, y: pos.y * factor, z: pos.z * factor },
      undefined as unknown as { x: number; y: number; z: number },
      transition
    );
  };

  return (
    <div className={styles.zoomControls} role="group" aria-label="Zoom controls">
      <button
        type="button"
        className={styles.zoomButton}
        onClick={() => scaleCamera(0.78)}
        aria-label="Zoom in"
        title="Zoom in"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M8 4v8 M4 8h8" />
        </svg>
      </button>
      <button
        type="button"
        className={styles.zoomButton}
        onClick={() => scaleCamera(1.28)}
        aria-label="Zoom out"
        title="Zoom out"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
          <path d="M4 8h8" />
        </svg>
      </button>
      <button
        type="button"
        className={styles.zoomButton}
        onClick={() => graphRef.current?.zoomToFit(transition * 2.5, 60)}
        aria-label="Fit all to view"
        title="Fit all (frame the whole graph)"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 6V3h3 M10 3h3v3 M3 10v3h3 M10 13h3v-3" />
        </svg>
      </button>
    </div>
  );
}

function Legend({ subjects }: { subjects: string[] }) {
  if (subjects.length === 0) return null;
  return (
    <div className={styles.legend} aria-label="Subject colour legend">
      {subjects.map((s) => (
        <div key={s} className={styles.legendItem}>
          <span
            className={styles.legendDot}
            style={{
              background: paletteFor(s).css,
              boxShadow: `0 0 6px ${paletteFor(s).css.replace("rgb", "rgba").replace(")", ",0.5)")}`,
            }}
          />
          <span className={styles.legendLabel}>{s}</span>
        </div>
      ))}
      <span className={styles.legendSep} aria-hidden />
      <span className={styles.legendHint}>drag · scroll · click</span>
    </div>
  );
}

interface DetailPanelProps {
  selected: SelectedConcept | null;
  onClose: () => void;
  onOpenInReader: (docId: string) => void;
}

function DetailPanel({ selected, onClose, onOpenInReader }: DetailPanelProps) {
  // Mount the panel always but slide it off-screen when nothing's
  // selected. The 260ms slide-in matches the spec's transform timing.
  const open = selected !== null;
  const data = selected?.data;

  // Tag class for subject pill. Defaults to "tagOther" if subject is
  // missing or unknown.
  const subject = data?.subject_name ?? null;
  const palette = subject ? paletteFor(subject) : FALLBACK_SUBJECT;

  return (
    <aside
      className={[styles.detailPanel, open ? styles.detailPanelOpen : ""].filter(Boolean).join(" ")}
      aria-label="Concept detail"
      aria-hidden={!open}
    >
      <div className={styles.dpHead}>
        <div className={styles.dpEyebrow}>
          <span className={styles.dpLabel}>Concept</span>
          <button type="button" className={styles.dpClose} onClick={onClose} aria-label="Close">
            ✕
          </button>
        </div>
        <h2 className={styles.dpTitle}>{data?.concept ?? "Loading…"}</h2>
        <div className={styles.dpTags}>
          {subject ? (
            <span
              className={styles.dpTag}
              style={{
                background: palette.css.replace("rgb", "rgba").replace(")", ",0.14)"),
                color: palette.css,
              }}
            >
              {subject}
            </span>
          ) : null}
        </div>
      </div>

      {data?.document_name ? (
        <div className={styles.dpSource}>
          <div className={styles.dpSecLabelMuted}>Source</div>
          <div className={styles.dpSourceText}>{data.document_name}</div>
        </div>
      ) : null}

      <div className={styles.dpBody}>
        {selected?.loading ? (
          <Text tone="secondary">Loading the concept's notes…</Text>
        ) : selected?.error ? (
          <Text tone="secondary">{selected.error}</Text>
        ) : data ? (
          <>
            {data.takeaway ? (
              <div className={styles.dpSection}>
                <div className={styles.dpSecLabelAccent}>Takeaway</div>
                <p className={styles.dpTakeaway}>{data.takeaway}</p>
              </div>
            ) : null}

            {data.claims.length > 0 ? (
              <div className={styles.dpSection}>
                <div className={styles.dpSecLabelMuted}>Claims</div>
                {data.claims.map((c, i) => (
                  <div
                    key={c.id}
                    className={styles.dpClaim}
                    style={{ animationDelay: `${i * 55}ms` }}
                  >
                    {c.claim_text}
                  </div>
                ))}
              </div>
            ) : null}

            {data.examples.length > 0 ? (
              <div className={styles.dpSection}>
                <div className={styles.dpSecLabelMuted}>Examples</div>
                {data.examples.map((e, i) => (
                  <div
                    key={e.id}
                    className={styles.dpClaim}
                    style={{ animationDelay: `${i * 55}ms` }}
                  >
                    {e.example_text}
                  </div>
                ))}
              </div>
            ) : null}

            {data.misconceptions.length > 0 ? (
              <div className={styles.dpSection}>
                <div className={styles.dpSecLabelMuted}>Misconceptions</div>
                {data.misconceptions.map((m, i) => (
                  <div
                    key={m.id}
                    className={styles.dpClaim}
                    style={{ animationDelay: `${i * 55}ms` }}
                  >
                    <strong>{m.label}.</strong> {m.description ?? ""}
                  </div>
                ))}
              </div>
            ) : null}

            {!data.takeaway &&
            data.claims.length === 0 &&
            data.examples.length === 0 &&
            data.misconceptions.length === 0 ? (
              <Text tone="tertiary">No indexed claims for this concept yet.</Text>
            ) : null}
          </>
        ) : null}
      </div>

      {data ? (
        <div className={styles.dpFoot}>
          <button
            type="button"
            className={styles.dpCta}
            // The explain payload has document_name but not the id —
            // we need the source node's document_id for navigation.
            // Fall back to no-op if it's somehow missing.
            onClick={() => {
              const node = selected ? findNodeDocId(selected.id) : null;
              if (node) onOpenInReader(node);
            }}
          >
            Open the source in Reader →
          </button>
        </div>
      ) : null}
    </aside>
  );
}

// ConceptExplainResponse doesn't carry the source document_id (just the
// filename), and we need an id to navigate. Stash a side-channel map of
// concept-id → doc-id at module scope so the detail panel can resolve.
//
// Why module-scope rather than a context: the panel is rendered inside
// the same component tree as the graph, but the graph's data isn't
// reactive to React in a clean way (it lives inside three.js). A simple
// map keeps the contract narrow.
const conceptDocIdMap = new Map<string, string>();
function findNodeDocId(conceptId: string): string | null {
  return conceptDocIdMap.get(conceptId) ?? null;
}

function EmptyState() {
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

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <span className={styles.stateEyebrow}>Graph unavailable</span>
        <Text as="h2" className={styles.stateHeading}>
          Couldn't load the concept graph.
        </Text>
        <Text tone="secondary">{message}</Text>
        <button type="button" className={styles.retryButton} onClick={onRetry}>
          Reload the graph
        </button>
      </Stack>
    </Card>
  );
}

