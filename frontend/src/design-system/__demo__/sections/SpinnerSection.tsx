import { Spinner, Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function SpinnerSection() {
  return (
    <SectionShell
      description="Small motion utility for loading and pending states."
      title="Spinner"
    >
      <Stack align="center" direction="horizontal" gap={4}>
        <Spinner size={16} />
        <Spinner size={20} />
        <Spinner size={24} />
        <Text tone="secondary">80–240 ms transitions, no motion library.</Text>
      </Stack>
    </SectionShell>
  );
}
