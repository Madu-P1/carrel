import { Badge, Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function StackSection() {
  return (
    <SectionShell
      description="Flex stack with semantic direction, gap, alignment, and wrap."
      title="Stack"
    >
      <Stack direction="horizontal" gap={3} wrap>
        <Badge tone="info">Horizontal</Badge>
        <Badge tone="success">Wrap</Badge>
        <Badge tone="warning">Gap 3</Badge>
      </Stack>
      <Stack gap={2}>
        <Text>Vertical stacks drive most of the shell rhythm.</Text>
        <Text tone="secondary">This is the default direction.</Text>
      </Stack>
    </SectionShell>
  );
}
