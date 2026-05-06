import { Stack, toast } from "@/design-system";

import { copyAskCardText, saveCitationAnchor } from "../anchorDrafts";
import styles from "../AskView.module.css";
import type { CitationRecord } from "../types";

import { AnswerFeedCard } from "./AnswerFeedCard";

interface AnswerSummaryProps {
  summary: string;
  citations: CitationRecord[];
  cacheHit: boolean;
  latencyMs: number;
  model: string;
  onRetry?: () => void;
}

function locationSummary(citations: CitationRecord[]): string | null {
  if (citations.length === 0) {
    return null;
  }
  const preview = citations.slice(0, 2).map((citation) =>
    [
      citation.document_name ?? citation.document_id ?? "Source",
      citation.page_num ? `p.${citation.page_num}` : null,
      citation.chunk_id ? `chunk ${citation.chunk_id}` : null
    ]
      .filter(Boolean)
      .join(" · ")
  );
  const extra = citations.length > 2 ? ` +${citations.length - 2} more` : "";
  return `${preview.join("  •  ")}${extra}`;
}

export function AnswerSummary({
  summary,
  citations,
  cacheHit,
  latencyMs,
  model,
  onRetry
}: AnswerSummaryProps) {
  if (!summary) {
    return null;
  }

  const citation = citations[0];
  const latencyToken = latencyMs > 0 ? `${(latencyMs / 1000).toFixed(1)}s` : "0.0s";
  const metaLocation = locationSummary(citations);

  return (
    <AnswerFeedCard
      actions={[
        {
          label: "Copy",
          onClick: () => {
            void copyAskCardText(summary)
              .then(() => {
                toast.success("Copied answer", "The grounded answer is on your clipboard.");
              })
              .catch(() => {
                toast.error("Copy failed", "Clipboard access is unavailable in this context.");
              });
          }
        },
        {
          label: "Retry the question",
          onClick: () => {
            onRetry?.();
          }
        },
        {
          label: "Save as anchor",
          onClick: () => {
            try {
              void saveCitationAnchor({
                claimText: "Grounded answer",
                quoteText: citation?.snippet || citation?.content || summary,
                sourceKind: "answer-summary",
                citation
              })
                .then(() => {
                  toast.success("Anchor saved", citation?.document_name ?? "Saved from this grounded answer.");
                })
                .catch(() => {
                  toast.error("Save failed", "Could not write this anchor.");
                });
            } catch {
              toast.error("Save failed", "Could not write this anchor.");
            }
          },
          disabled: citations.length === 0
        }
      ]}
      body={summary}
      evidence={
        <Stack className={styles.summaryEvidence} gap={1}>
          <div className={styles.summaryMetaTokens}>
            <span>{model || "no-model"}</span>
            <span aria-hidden>·</span>
            <span>{latencyToken}</span>
            <span aria-hidden>·</span>
            <span>{cacheHit ? "cache hit" : "cold call"}</span>
            <span aria-hidden>·</span>
            <span>{citations.length} source{citations.length === 1 ? "" : "s"}</span>
          </div>
          {metaLocation ? <div className={styles.feedCardLocation}>{metaLocation}</div> : null}
        </Stack>
      }
      title="Grounded answer"
    />
  );
}
