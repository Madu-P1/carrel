import { useEffect, useId, useRef, useState } from "preact/hooks";

import { registerFlight } from "@/features/shared/flightRegistry";
import { evidence, type EvidenceResolution } from "@/services/api/endpoints";

import styles from "../AskView.module.css";
import type { CitationRecord } from "../types";

interface CitationChipProps {
  citation: CitationRecord;
  /** One-based index as it appears in the answer. Rendered as `[N]` in mono. */
  index?: number;
  delayMs?: number;
  onClick?: (citation: CitationRecord) => void;
}

// Pick the best short preview text for the tooltip. Snippet is already
// designed for preview; content is the full chunk and gets truncated. Returns
// "" when neither is present — the chip then renders without a tooltip wrap.
function previewTextFor(citation: CitationRecord): string {
  const snippet = (citation.snippet ?? "").trim();
  if (snippet) return snippet.length > 220 ? `${snippet.slice(0, 220).trimEnd()}…` : snippet;
  const content = (citation.content ?? "").trim();
  if (content) return content.length > 220 ? `${content.slice(0, 220).trimEnd()}…` : content;
  return "";
}

export function CitationChip({ citation, index, delayMs = 0, onClick }: CitationChipProps) {
  const chipRef = useRef<HTMLButtonElement>(null);
  const hoverTimerRef = useRef<number | null>(null);
  const requestKeyRef = useRef<string>("");
  const previewId = useId();
  const [previewOpen, setPreviewOpen] = useState(false);
  const [resolved, setResolved] = useState<EvidenceResolution | null>(null);
  const [previewError, setPreviewError] = useState(false);

  useEffect(() => {
    setResolved(null);
    setPreviewError(false);
    requestKeyRef.current = "";
  }, [citation.chunk_id, citation.document_id]);

  const handleClick = () => {
    // SM-2: capture the chip's rect + HTML before navigation so the Reader
    // can spawn a ghost that flies from here to the target chunk.
    const el = chipRef.current;
    if (el && citation.chunk_id) {
      registerFlight({
        kind: "citation-chip",
        id: citation.chunk_id,
        rect: el.getBoundingClientRect(),
        html: el.outerHTML,
        docId: citation.document_id,
        chunkId: citation.chunk_id,
      });
    }
    onClick?.(citation);
  };

  const label =
    (citation.section ?? "Source")
    + (citation.page_num ? ` · p.${citation.page_num}` : "");
  // Screen-reader label per the brief §10: announce chunk source, not `[3]`.
  const srLabel = `citation ${index ?? ""}, ${label}. Click to open in reader.`.trim();

  const preview = previewTextFor(citation);
  const confidence = Math.round(((resolved?.confidence ?? citation.score ?? 0.7) || 0) * 100);
  const resolvedQuote = (resolved?.quote_text ?? preview).trim();
  const locationKind = resolved?.location_kind ?? (citation.chunk_id ? "chunk" : "page");
  const locationCopy = locationKind === "bbox" || locationKind === "text_offset"
    ? "Exact span"
    : "Approximate passage";
  const pageNum = resolved?.page_num ?? citation.page_num ?? null;
  const section = resolved?.section ?? citation.section ?? null;
  const documentName = resolved?.document_name ?? citation.document_name ?? "Source";

  const clearHoverTimer = () => {
    if (hoverTimerRef.current !== null) {
      window.clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
  };

  const openPreview = () => {
    clearHoverTimer();
    hoverTimerRef.current = window.setTimeout(() => setPreviewOpen(true), 220);
  };

  const closePreview = () => {
    clearHoverTimer();
    setPreviewOpen(false);
  };

  useEffect(() => {
    if (!previewOpen) {
      return undefined;
    }

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setPreviewOpen(false);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [previewOpen]);

  useEffect(() => {
    if (!previewOpen || !citation.document_id) {
      return undefined;
    }

    const requestKey = `${citation.document_id}:${citation.chunk_id ?? ""}`;
    if (requestKey === requestKeyRef.current && (resolved || previewError)) {
      return undefined;
    }
    requestKeyRef.current = requestKey;
    let active = true;
    setPreviewError(false);
    void evidence.resolve({
      documentId: citation.document_id,
      chunkId: citation.chunk_id
    })
      .then((result) => {
        if (active) {
          setResolved(result);
        }
      })
      .catch(() => {
        if (active) {
          setPreviewError(true);
        }
      });
    return () => {
      active = false;
    };
  }, [citation.chunk_id, citation.document_id, previewError, previewOpen, resolved]);

  useEffect(() => () => clearHoverTimer(), []);

  const chip = (
    <button
      className={[styles.citationChip, "anim-fadeUp"].join(" ")}
      data-chunk-id={citation.chunk_id}
      onClick={handleClick}
      ref={chipRef}
      style={{ animationDelay: `${delayMs}ms` }}
      type="button"
      aria-label={srLabel}
      aria-describedby={previewOpen && resolvedQuote ? previewId : undefined}
    >
      {typeof index === "number" && (
        <span className={styles.citationChipIndex} aria-hidden>
          [{index}]
        </span>
      )}
      <span className={styles.citationChipMeta} aria-hidden>
        {label}
      </span>
    </button>
  );

  return (
    <span
      className={styles.citationPreviewWrap}
      onBlur={closePreview}
      onFocus={openPreview}
      onMouseLeave={closePreview}
      onMouseOver={openPreview}
    >
      {chip}
      {previewOpen && resolvedQuote ? (
        <span className={styles.citationPreviewCard} id={previewId} role="tooltip">
          <span className={styles.citationPreviewHeader}>
            <span className={styles.citationPreviewSource}>{documentName}</span>
            <span className={styles.citationPreviewConfidence}>{confidence}%</span>
          </span>
          <span className={styles.citationPreviewMeta}>
            {pageNum ? `Page ${pageNum}` : "Page unknown"}
            {section ? ` · ${section}` : ""}
          </span>
          <span className={styles.citationPreviewQuote}>“{resolvedQuote}”</span>
          <span className={styles.citationPreviewFooter}>
            <span>{locationCopy}</span>
            <span>Click to inspect</span>
          </span>
        </span>
      ) : null}
    </span>
  );
}
