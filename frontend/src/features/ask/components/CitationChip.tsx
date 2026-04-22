import { useRef } from "preact/hooks";

import { registerFlight } from "@/features/shared/flightRegistry";

import type { CitationRecord } from "../types";
import styles from "../AskView.module.css";

interface CitationChipProps {
  citation: CitationRecord;
  /** One-based index as it appears in the answer. Rendered as `[N]` in mono. */
  index?: number;
  delayMs?: number;
  onClick?: (citation: CitationRecord) => void;
}

export function CitationChip({ citation, index, delayMs = 0, onClick }: CitationChipProps) {
  const chipRef = useRef<HTMLButtonElement>(null);

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

  return (
    <button
      className={[styles.citationChip, "anim-fadeUp"].join(" ")}
      data-chunk-id={citation.chunk_id}
      onClick={handleClick}
      ref={chipRef}
      style={{ animationDelay: `${delayMs}ms` }}
      type="button"
      aria-label={srLabel}
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
}
