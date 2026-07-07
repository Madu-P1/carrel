import { Badge, Card, Stack, Text } from "@/design-system";

import type { AskCard as AskCardData, AskCardsResponse } from "@/services/api/endpoints";

import { AskCard } from "./AskCard";
import styles from "./AskCardList.module.css";

export interface AskCardListProps {
  response: AskCardsResponse | null;
  pending: boolean;
  error: Error | null;
  onOpen?: (card: AskCardData) => void;
  onRetry?: () => void;
}

/**
 * Free-tier Ask result list. Renders three states explicitly so the
 * UI never shows a generic "no results" when the real cause is "the
 * library hasn't been ingested yet" — that distinction is what makes
 * the empty state actionable.
 *
 * Pending: skeleton-free for now (the AskView-level cold-load
 * indicator handles slow first responses). PR 4.2 can layer in a
 * proper card skeleton if user testing wants it.
 */
export function AskCardList({ response, pending, error, onOpen, onRetry }: AskCardListProps) {
  if (error) {
    return (
      <Card padding="lg" className={styles.errorCard}>
        <Stack gap={3}>
          <Stack gap={1}>
            <Badge tone="danger">Request failed</Badge>
            <Text as="h2" variant="h2" weight="bold">
              Could not retrieve cards
            </Text>
            <Text tone="secondary">{error.message}</Text>
          </Stack>
          {onRetry ? (
            <button type="button" onClick={onRetry} className={styles.retryButton}>
              Try again
            </button>
          ) : null}
        </Stack>
      </Card>
    );
  }

  if (pending && !response) {
    return (
      <div className={styles.loading}>
        <Text tone="secondary">Searching your library…</Text>
      </div>
    );
  }

  if (!response) {
    return null;
  }

  if (response.library.total_nodes === 0) {
    return (
      <Card padding="lg" className={styles.emptyCard}>
        <Stack gap={2}>
          <Badge tone="info">Library not yet indexed</Badge>
          <Text as="h2" variant="h2" weight="bold">
            No typed nodes in your library yet
          </Text>
          <Text tone="secondary">
            Cachet reads documents into a typed tree (headings, body
            paragraphs, footnotes, etc.) before answering. Set
            INGEST_USE_DOCLING=true in the backend env, then re-ingest
            your sources from the Library view.
          </Text>
        </Stack>
      </Card>
    );
  }

  if (response.cards.length === 0) {
    return (
      <Card padding="lg" className={styles.emptyCard}>
        <Stack gap={2}>
          <Text as="h2" variant="h2" weight="bold">
            No matching passages
          </Text>
          <Text tone="secondary">
            Cachet searched {response.library.total_nodes.toLocaleString()}{" "}
            indexed passages and found nothing close enough to surface.
            Try rephrasing the question or adding more context.
          </Text>
        </Stack>
      </Card>
    );
  }

  return (
    <div className={styles.list} role="list" aria-label="Most likely answers in your library">
      <div className={styles.eyebrow}>
        <span>Most likely answers in your library</span>
        {response.rerank_used ? (
          <span title="Cross-encoder rerank applied">
            <Badge tone="info" className={styles.rerankBadge}>
              reranked
            </Badge>
          </span>
        ) : null}
      </div>
      {response.cards.map((card, index) => (
        <div role="listitem" key={card.node_id}>
          <AskCard card={card} index={index} onOpen={onOpen} />
        </div>
      ))}
    </div>
  );
}
