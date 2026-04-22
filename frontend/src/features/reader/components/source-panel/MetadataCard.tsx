import type { DocumentDetail } from "@/services/api/endpoints";
import { Badge, Stack, Text } from "@/design-system";

import styles from "./SourcePanel.module.css";

type ReaderDocument = DocumentDetail["document"];

function confidenceTone(confidence: number | null | undefined): "success" | "warning" | "danger" | "neutral" {
  if (typeof confidence !== "number") {
    return "neutral";
  }
  if (confidence >= 0.85) {
    return "success";
  }
  if (confidence >= 0.65) {
    return "warning";
  }
  return "danger";
}

export function MetadataCard({
  chunkCount,
  doc,
  summary
}: {
  chunkCount: number;
  doc: ReaderDocument;
  summary: string;
}) {
  return (
    <section className={styles.card}>
      <Stack gap={2}>
        <Stack align="center" direction="horizontal" gap={2} wrap>
          <Badge tone="info">{doc.file_type?.toUpperCase() || "DOC"}</Badge>
          {doc.subject_name ? <Badge>{doc.subject_name}</Badge> : null}
          <Badge tone={confidenceTone(doc.confidence)}>
            Confidence {typeof doc.confidence === "number" ? `${Math.round(doc.confidence * 100)}%` : "n/a"}
          </Badge>
        </Stack>
        <Text as="h3" variant="h2" weight="bold">
          {doc.filename}
        </Text>
        {summary ? <Text tone="secondary">{summary}</Text> : null}
      </Stack>

      <div className={styles.metaGrid}>
        <div className={styles.metaRow}>
          <Text tone="tertiary" variant="caption">
            Pages
          </Text>
          <Text>{doc.page_count ?? "Unknown"}</Text>
        </div>
        <div className={styles.metaRow}>
          <Text tone="tertiary" variant="caption">
            Chunks
          </Text>
          <Text>{chunkCount}</Text>
        </div>
        <div className={styles.metaRow}>
          <Text tone="tertiary" variant="caption">
            Status
          </Text>
          <Text>{doc.status ?? "ready"}</Text>
        </div>
        <div className={styles.metaRow}>
          <Text tone="tertiary" variant="caption">
            Updated
          </Text>
          <Text>{doc.updated_at ?? doc.upload_date ?? "Unknown"}</Text>
        </div>
      </div>
    </section>
  );
}
