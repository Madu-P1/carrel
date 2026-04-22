import { Card, Spinner, Stack, Text } from "@/design-system";

import styles from "../ReaderView.module.css";

export function ReaderLoadingState() {
  return (
    <Card className={styles.stateCard} padding="lg">
      <Stack align="center" gap={4}>
        <Spinner label="Loading reader" size={24} />
        <Text as="h2" variant="h2" weight="semibold">
          Loading source preview...
        </Text>
        <Text tone="secondary">Preparing metadata and the first page canvas.</Text>
      </Stack>
    </Card>
  );
}
