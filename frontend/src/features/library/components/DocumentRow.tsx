import { useEffect, useRef, useState } from "preact/hooks";

import { Badge, Button, Stack, Text } from "@/design-system";
import { registerFlight } from "@/features/shared/flightRegistry";
import type { DocumentRow as DocumentRowType } from "@/services/api/endpoints";

import styles from "./DocumentRow.module.css";

interface DocumentRowProps {
  document: DocumentRowType;
  onDelete: () => void;
  onOpen: () => void;
}

function confidenceTone(confidence: number): "success" | "warning" | "danger" {
  if (confidence >= 0.85) {
    return "success";
  }
  if (confidence >= 0.65) {
    return "warning";
  }
  return "danger";
}

export function DocumentRow({ document, onDelete, onOpen }: DocumentRowProps) {
  const rootRef = useRef<HTMLButtonElement>(null);
  const previousStatus = useRef<string | null>(null);
  const [isPulsing, setIsPulsing] = useState(false);

  // SM-4: when the doc transitions from "processing" → "ready", pulse once.
  useEffect(() => {
    const prev = previousStatus.current;
    const next = document.status ?? null;
    if (prev !== null && prev.toLowerCase() === "processing" && next?.toLowerCase() === "ready") {
      setIsPulsing(true);
      const el = rootRef.current;
      if (el) {
        const handler = () => setIsPulsing(false);
        el.addEventListener("animationend", handler, { once: true });
        return () => el.removeEventListener("animationend", handler);
      }
    }
    previousStatus.current = next;
    return undefined;
  }, [document.status]);

  const handleCardClick = (event: MouseEvent) => {
    // SM-1: capture the card's rect before navigation so ReaderView can
    // FLIP its title bar into place from here.
    const el = event.currentTarget as HTMLElement | null;
    if (el) {
      registerFlight({
        kind: "doc-card",
        id: document.id,
        rect: el.getBoundingClientRect(),
      });
    }
    onOpen();
  };

  return (
    <button
      aria-label={`Open ${document.filename}`}
      className={[styles.row, isPulsing ? "anim-pulseOnce" : ""].filter(Boolean).join(" ")}
      data-doc-id={document.id}
      data-status={document.status ?? undefined}
      onClick={handleCardClick}
      ref={rootRef}
      type="button"
    >
      <div className={styles.header}>
        <div className={styles.titleGroup}>
          <Text as="span" variant="h3" weight="semibold">
            {document.filename}
          </Text>
          <Text as="span" tone="secondary">
            {document.summary || "No summary available yet."}
          </Text>
        </div>
        <Stack direction="horizontal" gap={2} wrap>
          <Badge tone="neutral">{(document.file_type || "file").toUpperCase()}</Badge>
          {document.confidence !== null && document.confidence !== undefined ? (
            <Badge tone={confidenceTone(document.confidence)}>
              {Math.round(document.confidence * 100)}% confidence
            </Badge>
          ) : null}
        </Stack>
      </div>

      <div className={styles.meta}>
        <Text as="span" tone="tertiary">
          {document.page_count ? `${document.page_count} page${document.page_count === 1 ? "" : "s"}` : "Unknown length"}
        </Text>
        <Text as="span" tone="tertiary">
          {document.status || "unknown"}
        </Text>
        <Text as="span" tone="tertiary">
          {document.concept_count} concepts
        </Text>
        <Text as="span" tone="tertiary">
          {document.question_count} questions
        </Text>
      </div>

      <div className={styles.actions}>
        <Button
          onClick={(event) => {
            event.stopPropagation();
            // Same capture as card-level click, using the row element so the
            // FLIP source rect still covers the whole card.
            if (rootRef.current) {
              registerFlight({
                kind: "doc-card",
                id: document.id,
                rect: rootRef.current.getBoundingClientRect(),
              });
            }
            onOpen();
          }}
          variant="secondary"
        >
          Open
        </Button>
        <Button
          onClick={(event) => {
            event.stopPropagation();
            onDelete();
          }}
          variant="ghost"
        >
          Delete
        </Button>
      </div>
    </button>
  );
}
