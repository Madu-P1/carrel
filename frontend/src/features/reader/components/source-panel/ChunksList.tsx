import { navigateTo } from "@/app/shell/useAppShell";
import type { DocumentDetail } from "@/services/api/endpoints";

import { buildReaderChunkPath } from "../../hooks/useChunkDeepLink";
import { requestReaderPage } from "../../state";

import { ChunkRow } from "./ChunkRow";
import { EmptyState } from "./EmptyState";
import styles from "./SourcePanel.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

/**
 * Group chunks by their originating page. Non-paginated sources (docx,
 * markdown, etc.) fall into a single "Document" bucket so the same
 * component can render both cases without a separate code path.
 */
function groupChunksByPage(chunks: ReaderChunk[]) {
  const groups = new Map<string, ReaderChunk[]>();

  for (const chunk of chunks) {
    const key = chunk.page_num != null ? `Page ${chunk.page_num}` : "Document";
    const group = groups.get(key);
    if (group) {
      group.push(chunk);
    } else {
      groups.set(key, [chunk]);
    }
  }

  return Array.from(groups.entries());
}

interface ChunksListProps {
  chunks: ReaderChunk[];
  docId: string;
}

export function ChunksList({ chunks, docId }: ChunksListProps) {
  if (chunks.length === 0) {
    return (
      <EmptyState
        icon="doc"
        title="No chunks extracted yet."
        description="Chunks appear once the parser finishes. Re-run the import if this stays empty for more than a minute."
      />
    );
  }

  const groups = groupChunksByPage(chunks);

  return (
    <div className={styles.list}>
      {groups.map(([label, group]) => (
        <section className={styles.pageGroup} key={label}>
          <header className={styles.pageLabel}>{label}</header>
          <ul className={styles.rowList}>
            {group.map((chunk) => (
              <li key={chunk.id}>
                <ChunkRow
                  chunk={chunk}
                  onSelect={(selectedChunk) => {
                    navigateTo(buildReaderChunkPath(docId, selectedChunk.id));
                    if (selectedChunk.page_num != null) {
                      requestReaderPage(selectedChunk.page_num);
                    }
                  }}
                />
              </li>
            ))}
          </ul>
        </section>
      ))}
    </div>
  );
}
