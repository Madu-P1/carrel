import { Card, Stack, Text } from "@/design-system";

import styles from "./SectionShell.module.css";
import { SectionShell } from "./SectionShell";

export function CardSection() {
  return (
    <SectionShell
      description="Bounded surfaces for panes, artifacts, and empty states."
      title="Card"
    >
      <div className={styles.grid}>
        <Card padding="sm">
          <Text variant="h3" weight="semibold">
            Small card
          </Text>
        </Card>
        <Card padding="md">
          <Stack gap={2}>
            <Text variant="h3" weight="semibold">
              Medium card
            </Text>
            <Text tone="secondary">Default density for list rows and summaries.</Text>
          </Stack>
        </Card>
        <Card padding="lg">
          <Text variant="h3" weight="semibold">
            Large card
          </Text>
        </Card>
      </div>
    </SectionShell>
  );
}
