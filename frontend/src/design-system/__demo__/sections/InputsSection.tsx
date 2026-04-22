import { Icon, Input, Stack } from "@/design-system";

import styles from "./SectionShell.module.css";
import { SectionShell } from "./SectionShell";

export function InputsSection() {
  return (
    <SectionShell
      description="Labeled, helper, and error states with leading icons."
      title="Inputs"
    >
      <div className={styles.grid}>
        <Input
          helpText="Ask about a concept, span, or source."
          label="Ask Einstein"
          leadingIcon={<Icon name="ask" />}
          placeholder="How does mitosis differ from meiosis?"
        />
        <Input
          error="A source title is required."
          label="Source title"
          leadingIcon={<Icon name="doc" />}
          placeholder="Taxation and Business Law"
        />
      </div>
      <Stack direction="horizontal" gap={4}>
        <Input label="Quick filter" placeholder="Search…" />
      </Stack>
    </SectionShell>
  );
}
