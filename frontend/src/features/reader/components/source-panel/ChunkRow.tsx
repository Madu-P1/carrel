import { useEffect, useRef } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";
import { Text } from "@/design-system";

import { readerState } from "../../state";
import styles from "./SourcePanel.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

interface ChunkRowProps {
  chunk: ReaderChunk;
  onSelect: (chunk: ReaderChunk) => void;
}

export function ChunkRow({ chunk, onSelect }: ChunkRowProps) {
  const rowRef = useRef<HTMLButtonElement>(null);
  const highlighted = readerState.highlightedChunkId.value === chunk.id;

  useEffect(() => {
    if (highlighted) {
      rowRef.current?.scrollIntoView({ block: "center" });
    }
  }, [highlighted]);

  return (
    <button
      className={[
        styles.chunkButton,
        highlighted ? styles.chunkButtonHighlighted : ""
      ]
        .filter(Boolean)
        .join(" ")}
      data-chunk-id={chunk.id}
      onClick={() => onSelect(chunk)}
      ref={rowRef}
      type="button"
    >
      <div className={styles.chunkMeta}>
        <Text tone="tertiary" variant="caption">
          {chunk.section || "Source chunk"}
        </Text>
        {chunk.page_num != null ? (
          <Text tone="tertiary" variant="caption">
            p. {chunk.page_num}
          </Text>
        ) : null}
      </div>
      <Text className={styles.chunkPreview}>{chunk.content}</Text>
    </button>
  );
}
