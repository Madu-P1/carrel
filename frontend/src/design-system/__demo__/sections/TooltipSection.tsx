import { Button, Tooltip } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function TooltipSection() {
  return (
    <SectionShell
      description="Hover hint with a 400 ms delay and escape-to-dismiss."
      title="Tooltip"
    >
      <Tooltip content="Jump to the cited span in the Reader.">
        <Button variant="secondary">Hover for context</Button>
      </Tooltip>
    </SectionShell>
  );
}
