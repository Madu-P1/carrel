import { Badge, Button, Stack, Text, toast } from "@/design-system";
import type { EvidenceResolution } from "@/services/api/endpoints";
import { anchors } from "@/services/api/endpoints";

import styles from "./SourcePanel.module.css";

export function EvidenceInspector({ evidence }: { evidence: EvidenceResolution }) {
  const exact = evidence.location_kind === "bbox" || evidence.location_kind === "text_offset";
  return (
    <Stack gap={4}>
      <Stack gap={2}>
        <Badge tone={exact ? "success" : "warning"}>
          {exact ? "Exact evidence" : "Approximate location"}
        </Badge>
        <Text as="h3" variant="h3" weight="semibold">
          {evidence.section || "Evidence"}
        </Text>
        <Text tone="tertiary" variant="caption">
          {evidence.document_name}
          {evidence.page_num ? ` · p. ${evidence.page_num}` : ""}
        </Text>
      </Stack>
      <blockquote className={styles.evidenceQuote}>{evidence.quote_text}</blockquote>
      <Text tone="secondary">
        {exact
          ? "Carrel resolved this citation to a precise source span."
          : "Carrel resolved this citation to the nearest source chunk. Treat the highlighted passage as approximate."}
      </Text>
      <Button
        onClick={() => {
          void anchors.create({
            document_id: evidence.document_id,
            chunk_id: evidence.chunk_id,
            page_num: evidence.page_num,
            quote_text: evidence.quote_text,
            origin: "ai_answer_citation",
            confidence: evidence.confidence
          })
            .then(() => toast.success("Anchor saved", evidence.document_name))
            .catch(() => toast.error("Save failed", "Carrel could not save this evidence as an Anchor."));
        }}
        variant="secondary"
      >
        Save as anchor
      </Button>
    </Stack>
  );
}
