import { Divider, Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function DividerSection() {
  return (
    <SectionShell
      description="Subtle separators for panes, toolbars, and menus."
      title="Divider"
    >
      <Divider />
      <Stack align="stretch" direction="horizontal" gap={4}>
        <Text>Left pane</Text>
        <Divider orientation="vertical" />
        <Text>Right pane</Text>
      </Stack>
    </SectionShell>
  );
}
