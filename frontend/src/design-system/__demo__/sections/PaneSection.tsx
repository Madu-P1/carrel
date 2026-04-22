import { Pane, Text } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function PaneSection() {
  return (
    <SectionShell
      description="Collapsible panel scaffold for the future three-pane shell."
      title="Pane"
    >
      <Pane title="Reader Outline">
        <Text tone="secondary">
          Future shell panes will start from this scaffold and gain split-view
          ownership in PR-E2.
        </Text>
      </Pane>
    </SectionShell>
  );
}
