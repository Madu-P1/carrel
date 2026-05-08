import { Badge, Button, Card, Stack, Text } from "@/design-system";

import type { AskCard as AskCardData } from "@/services/api/endpoints";
import styles from "./AskCard.module.css";

export interface AskCardProps {
  card: AskCardData;
  index: number;
  /**
   * Click handler for the Open button. Passed the full card so the
   * caller can route to the reader pane with everything it needs to
   * land on the right passage (`doc_id`, `page`, `char_start`,
   * `char_end`).
   */
  onOpen?: (card: AskCardData) => void;
}

function _confidenceBadgeTone(score: number | null): "success" | "info" | "neutral" | null {
  if (score === null) return null;
  if (score >= 0.85) return "success";
  if (score >= 0.6) return "info";
  return "neutral";
}

function _sourcesHint(sources: ReadonlyArray<"fts" | "vec">): string {
  if (sources.length === 2) return "matched on keyword + meaning";
  if (sources[0] === "fts") return "keyword match";
  if (sources[0] === "vec") return "semantic match";
  return "";
}

/**
 * Free-tier Ask card. Citation-grounded passage with no synthesis.
 *
 * Layout (per the parent algorithm spec § Stage 4 Render):
 *   [eyebrow] heading_path · type
 *   [body]    verbatim_text (serif italic, large)
 *   [footer]  filename, page · confidence · [Open →]
 */
export function AskCard({ card, index, onOpen }: AskCardProps) {
  const tone = _confidenceBadgeTone(card.rerank_score);
  const sourcesHint = _sourcesHint(card.sources);
  const heading = card.heading_path || "Untitled section";
  const sourceLine = [
    card.filename ?? "Unknown source",
    card.page !== null && card.page !== undefined ? `p. ${card.page}` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <Card padding="md" className={styles.card} data-card-index={index}>
      <Stack gap={3}>
        <div className={styles.eyebrow}>
          <span className={styles.eyebrowPath}>{heading}</span>
          <span className={styles.eyebrowDot} aria-hidden="true">·</span>
          <span className={styles.eyebrowType}>{card.node_type}</span>
        </div>

        <blockquote className={styles.quote}>
          <span aria-hidden="true" className={styles.quoteMark}>“</span>
          {card.verbatim_text}
          <span aria-hidden="true" className={styles.quoteMark}>”</span>
        </blockquote>

        <div className={styles.footer}>
          <Text className={styles.source}>{sourceLine}</Text>
          <div className={styles.footerRight}>
            {tone !== null && card.rerank_score !== null ? (
              <span title={`reranked confidence: ${(card.rerank_score * 100).toFixed(0)}%`}>
                <Badge tone={tone}>
                  {(card.rerank_score * 100).toFixed(0)}% match
                </Badge>
              </span>
            ) : null}
            {sourcesHint ? (
              <Text className={styles.sourcesHint} tone="secondary">
                {sourcesHint}
              </Text>
            ) : null}
            <Button
              variant="secondary"
              size="sm"
              onClick={() => onOpen?.(card)}
              type="button"
              aria-label={`Open ${card.filename ?? "source"} ${
                card.page !== null && card.page !== undefined ? `page ${card.page}` : ""
              } in reader`}
            >
              Open <span aria-hidden="true">→</span>
            </Button>
          </div>
        </div>
      </Stack>
    </Card>
  );
}
