import { Badge, Stack, Text } from "@/design-system";

import styles from "./DemoPage.module.css";
import { BadgesSection } from "./sections/BadgesSection";
import { BoxSection } from "./sections/BoxSection";
import { ButtonsSection } from "./sections/ButtonsSection";
import { CardSection } from "./sections/CardSection";
import { DialogSection } from "./sections/DialogSection";
import { DividerSection } from "./sections/DividerSection";
import { IconsSection } from "./sections/IconsSection";
import { InputsSection } from "./sections/InputsSection";
import { PaneSection } from "./sections/PaneSection";
import { ScrollAreaSection } from "./sections/ScrollAreaSection";
import { SpinnerSection } from "./sections/SpinnerSection";
import { StackSection } from "./sections/StackSection";
import { TextSection } from "./sections/TextSection";
import { TooltipSection } from "./sections/TooltipSection";

export function DemoPage() {
  return (
    <main className={styles.page}>
      <Stack gap={8}>
        <Stack gap={3}>
          <Badge tone="info">Cachet Design System</Badge>
          <Text as="h1" variant="display" weight="bold">
            PR-E1 Demo Surface
          </Text>
          <Text tone="secondary">
            A flat gallery of primitives, tokens, and interactive states. This
            is intentionally throwaway and will become a real shell in PR-E2.
          </Text>
        </Stack>
        <ButtonsSection />
        <InputsSection />
        <BadgesSection />
        <TextSection />
        <BoxSection />
        <StackSection />
        <IconsSection />
        <SpinnerSection />
        <CardSection />
        <DividerSection />
        <PaneSection />
        <TooltipSection />
        <DialogSection />
        <ScrollAreaSection />
      </Stack>
    </main>
  );
}
