import { useEffect, useRef } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";

import { readerState } from "../../state";

import styles from "./SourcePanel.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

interface ChunkRowProps {
  chunk: ReaderChunk;
  onSelect: (chunk: ReaderChunk) => void;
}

/**
 * ChunkRow — standardized row treatment.
 *
 * Spec from the UI pass:
 *   padding   --space-3 vertical, --space-4 horizontal
 *   separator 1px hairline between rows (not 2px — 2px was visual noise
 *             at 320px column width)
 *   layout    title line (section · page) in primary tone, preview in
 *             secondary tone, 2-line clamped
 *   radius    --radius-card on hover so the click target feels discrete
 *   active    --state-bg-selected + left-edge accent rail
 *
 * Whole row is the click target — a button wrapping both lines — so the
 * hover + focus ring covers everything and there's no "the title isn't
 * clickable but the body is" confusion.
 */
export function ChunkRow({ chunk, onSelect }: ChunkRowProps) {
  const rowRef = useRef<HTMLButtonElement>(null);
  const highlighted = readerState.highlightedChunkId.value === chunk.id;

  useEffect(() => {
    if (!highlighted) return;
    const el = rowRef.current;
    // JSDOM doesn't implement scrollIntoView — guard so the test
    // environment doesn't throw, while still scrolling in a real
    // browser where the function exists.
    if (el && typeof el.scrollIntoView === "function") {
      el.scrollIntoView({ block: "center" });
    }
  }, [highlighted]);

  const sectionLabel = chunk.section || "Source chunk";
  const locationLabel =
    chunk.page_num != null ? `p. ${chunk.page_num}` : null;

  return (
    <button
      aria-current={highlighted ? "true" : undefined}
      className={[
        styles.chunkButton,
        highlighted ? styles.chunkButtonActive : ""
      ]
        .filter(Boolean)
        .join(" ")}
      data-chunk-id={chunk.id}
      onClick={() => onSelect(chunk)}
      ref={rowRef}
      type="button"
    >
      <div className={styles.rowHeader}>
        <span className={styles.rowTitle}>{sectionLabel}</span>
        {locationLabel ? (
          <span className={styles.rowLocation}>{locationLabel}</span>
        ) : null}
      </div>
      <p className={styles.rowPreview}>{chunk.content}</p>
    </button>
  );
}
