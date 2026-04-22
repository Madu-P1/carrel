import { Box, ScrollArea, Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function ScrollAreaSection() {
  return (
    <SectionShell
      description="Styled overflow region for lists, outlines, and inspectors."
      title="ScrollArea"
    >
      <ScrollArea style={{ maxHeight: "180px" }}>
        <Stack gap={2}>
          {Array.from({ length: 12 }, (_, index) => (
            <Box
              border
              key={index}
              padding={3}
              radius={3}
              surface="muted"
            >
              <Text>Scrollable item {index + 1}</Text>
            </Box>
          ))}
        </Stack>
      </ScrollArea>
    </SectionShell>
  );
}
