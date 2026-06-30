import type { DocumentDetailDocument } from "@/services/api/endpoints";
import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";

import styles from "../ReaderView.module.css";

type PlaceholderReason = "no-doc-selected" | "non-pdf" | "not-found" | "empty-content";

interface ReaderPlaceholderProps {
  metadata?: DocumentDetailDocument;
  reason: PlaceholderReason;
}

function badgeTone(reason: PlaceholderReason): "info" | "warning" | "danger" {
  if (reason === "non-pdf") {
    return "warning";
  }
  if (reason === "not-found") {
    return "danger";
  }
  return "info";
}

function copyForReason(reason: PlaceholderReason, metadata?: DocumentDetailDocument) {
  if (reason === "non-pdf") {
    return {
      body: `Preview not implemented yet for ${(metadata?.file_type ?? "this").toUpperCase()} files.`,
      eyebrow: "Non-PDF preview",
      title: metadata?.filename ?? "This source is not a PDF"
    };
  }

  if (reason === "not-found") {
    return {
      body: "We could not find that document in your workspace. Return to Library and choose another source.",
      eyebrow: "Missing document",
      title: "This source is no longer available."
    };
  }

  if (reason === "empty-content") {
    return {
      body: "This document was processed but contains no extractable text.",
      eyebrow: "Empty document",
      title: "No readable content."
    };
  }

  return {
    body: "Pick a document from Library to open the new PDF reader shell.",
    eyebrow: "Reader",
    title: "No source selected yet."
  };
}

export function ReaderPlaceholder({ metadata, reason }: ReaderPlaceholderProps) {
  const copy = copyForReason(reason, metadata);
  // The "pick a source" CTA makes sense for no-doc-selected, not-found, and
  // empty-content — in all three the fix is to go back and pick another
  // source. For non-pdf we leave it off; the user is already looking at a
  // source.
  const showLibraryAction =
    reason === "no-doc-selected" || reason === "not-found" || reason === "empty-content";

  return (
    <Card className={styles.stateCard} padding="lg">
      <Stack gap={4}>
        <Badge tone={badgeTone(reason)}>{copy.eyebrow}</Badge>
        <Text as="h2" variant="h1" weight="bold">
          {copy.title}
        </Text>
        <Text tone="secondary">{copy.body}</Text>
        {showLibraryAction ? (
          <Stack direction="horizontal" gap={2}>
            <Button
              keyHint="⌘3"
              leadingIcon={<Icon name="library" />}
              onClick={() => navigateTo("/library")}
            >
              Open Library
            </Button>
          </Stack>
        ) : null}
      </Stack>
    </Card>
  );
}
