import type { ComponentChildren } from "preact";

import { Card, Stack, Text } from "@/design-system";

import styles from "./SectionShell.module.css";

export interface SectionShellProps {
  title: string;
  description: string;
  children?: ComponentChildren;
}

export function SectionShell({
  title,
  description,
  children
}: SectionShellProps) {
  return (
    <section className={styles.section}>
      <header className={styles.header}>
        <Text as="h2" variant="h1" weight="bold">
          {title}
        </Text>
        <Text tone="secondary">{description}</Text>
      </header>
      <Card padding="lg">
        <Stack gap={4}>{children}</Stack>
      </Card>
    </section>
  );
}
