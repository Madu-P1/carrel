import { Badge, Stack } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function BadgesSection() {
  return (
    <SectionShell
      description="Confidence, status, and freshness chips."
      title="Badges"
    >
      <Stack direction="horizontal" gap={3} wrap>
        <Badge>Neutral</Badge>
        <Badge tone="success">Grounded</Badge>
        <Badge tone="warning">Needs OCR</Badge>
        <Badge tone="danger">Blocked</Badge>
        <Badge tone="info">Fresh</Badge>
      </Stack>
    </SectionShell>
  );
}
