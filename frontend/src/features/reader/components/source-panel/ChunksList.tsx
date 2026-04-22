import type { DocumentDetail } from "@/services/api/endpoints";
import { Pane, Text } from "@/design-system";

import { navigateTo } from "@/app/shell/useAppShell";
import { requestReaderPage } from "../../state";
import { buildReaderChunkPath } from "../../hooks/useChunkDeepLink";
import { ChunkRow } from "./ChunkRow";
import styles from "./SourcePanel.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

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

export function ChunksList({ chunks, docId }: { chunks: ReaderChunk[]; docId: string }) {
  const groups = groupChunksByPage(chunks);

  return (
    <Pane title={`Chunks (${chunks.length})`}>
      <div className={styles.list}>
        {groups.map(([label, group]) => (
          <section className={styles.pageGroup} key={label}>
            <Text className={styles.pageLabel} tone="tertiary" variant="caption" weight="semibold">
              {label}
            </Text>
            {group.map((chunk) => (
              <ChunkRow
                chunk={chunk}
                key={chunk.id}
                onSelect={(selectedChunk) => {
                  navigateTo(buildReaderChunkPath(docId, selectedChunk.id));
                  if (selectedChunk.page_num != null) {
                    requestReaderPage(selectedChunk.page_num);
                  }
                }}
              />
            ))}
          </section>
        ))}
      </div>
    </Pane>
  );
}
