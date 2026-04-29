import { Button, Card, Stack, Text } from "@/design-system";

import styles from "../ReaderView.module.css";

interface ReaderErrorStateProps {
  error: Error;
  onRetry?: () => void;
}

export function ReaderErrorState({ error, onRetry }: ReaderErrorStateProps) {
  return (
    <Card className={styles.stateCard} padding="lg">
      <Stack gap={4}>
        <Text as="h2" variant="h1" weight="bold">
          Reader preview failed to load.
        </Text>
        <Text tone="secondary">{error.message || "Unknown reader error."}</Text>
        {onRetry ? (
          <Button onClick={onRetry} variant="secondary">
            Reload the document
          </Button>
        ) : null}
      </Stack>
    </Card>
  );
}
