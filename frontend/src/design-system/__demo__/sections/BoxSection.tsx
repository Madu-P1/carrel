import { Box, Stack, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";
import styles from "./SectionShell.module.css";

export function BoxSection() {
  return (
    <SectionShell
      description="Foundation layout surface with padding, radius, border, and tone."
      title="Box"
    >
      <div className={styles.grid}>
        <Box border padding={4} radius={4} surface="muted">
          <Text>Muted surface</Text>
        </Box>
        <Box border padding={4} radius={4} surface="elevated">
          <Text>Elevated surface</Text>
        </Box>
        <Box border padding={4} radius="full" surface="overlay">
          <Text>Overlay pill</Text>
        </Box>
      </div>
      <Stack direction="horizontal" gap={3}>
        <Box border padding={2} radius={2}>
          <Text variant="caption">P2</Text>
        </Box>
        <Box border padding={6} radius={5}>
          <Text>Padding 6, radius 5</Text>
        </Box>
      </Stack>
    </SectionShell>
  );
}
