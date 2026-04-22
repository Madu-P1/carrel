import { Card, Stack, Text } from "@/design-system";

import styles from "../AskView.module.css";

interface AnswerSummaryProps {
  summary: string;
}

export function AnswerSummary({ summary }: AnswerSummaryProps) {
  if (!summary) {
    return null;
  }

  return (
    <Card className={[styles.summaryCard, "anim-fadeUp"].join(" ")} padding="lg">
      <Stack gap={2}>
        <Text as="h2" variant="h1" weight="bold">
          Grounded answer
        </Text>
        <Text>{summary}</Text>
      </Stack>
    </Card>
  );
}
