import { Button, Icon, Stack } from "@/design-system";

import { SectionShell } from "./SectionShell";
import styles from "./SectionShell.module.css";

export function ButtonsSection() {
  return (
    <SectionShell
      description="Primary, secondary, ghost, danger, and loading states."
      title="Buttons"
    >
      <div className={styles.grid}>
        <Button leadingIcon={<Icon name="plus" />}>Create workspace</Button>
        <Button variant="secondary" leadingIcon={<Icon name="settings" />}>
          Settings
        </Button>
        <Button variant="ghost" leadingIcon={<Icon name="search" />}>
          Search
        </Button>
        <Button variant="danger" leadingIcon={<Icon name="x" />}>
          Delete source
        </Button>
      </div>
      <Stack direction="horizontal" gap={3}>
        <Button size="sm">Small</Button>
        <Button size="md">Medium</Button>
        <Button size="lg">Large</Button>
        <Button isLoading>Loading</Button>
      </Stack>
    </SectionShell>
  );
}
