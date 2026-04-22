import { Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function TextSection() {
  return (
    <SectionShell
      description="System typography only, tuned for native-feel density."
      title="Text"
    >
      <Stack gap={2}>
        <Text variant="display" weight="bold">
          Display
        </Text>
        <Text variant="h1" weight="bold">
          Heading 1
        </Text>
        <Text variant="h2" weight="semibold">
          Heading 2
        </Text>
        <Text variant="h3" weight="semibold">
          Heading 3
        </Text>
        <Text>Body copy for lists, notes, and grounded answers.</Text>
        <Text tone="secondary">Secondary body text for supporting context.</Text>
        <Text tone="tertiary" variant="caption">
          Caption and metadata.
        </Text>
      </Stack>
    </SectionShell>
  );
}
