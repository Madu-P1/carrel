import type { DocumentDetail } from "@/services/api/endpoints";
import { Stack } from "@/design-system";

import styles from "./SourcePanel.module.css";
import { ChunksList } from "./ChunksList";
import { ConceptsList } from "./ConceptsList";
import { MetadataCard } from "./MetadataCard";
import { NotesList } from "./NotesList";

interface SourcePanelProps {
  detail: DocumentDetail;
  docId: string;
}

export function SourcePanel({ detail, docId }: SourcePanelProps) {
  const chunks = detail.chunks ?? [];
  const concepts = detail.concepts ?? [];
  const notes = Array.isArray((detail as Record<string, unknown>).notes)
    ? (((detail as Record<string, unknown>).notes as unknown[]) as Array<{ content?: string; title?: string }>)
    : [];

  return (
    <Stack className={styles.panel} gap={4}>
      <MetadataCard chunkCount={chunks.length} doc={detail.document} summary={detail.summary} />
      <ChunksList chunks={chunks} docId={docId} />
      {concepts.length ? <ConceptsList concepts={concepts} /> : null}
      {notes.length ? <NotesList notes={notes} /> : null}
    </Stack>
  );
}
