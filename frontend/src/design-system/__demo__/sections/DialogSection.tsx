import { useState } from "preact/hooks";

import { Button, Dialog, Input, Stack } from "@/design-system";

import { SectionShell } from "./SectionShell";

export function DialogSection() {
  const [open, setOpen] = useState(false);

  return (
    <SectionShell
      description="Modal scaffolding with escape close and focus management."
      title="Dialog"
    >
      <Button onClick={() => setOpen(true)}>Open dialog</Button>
      <Dialog
        actions={
          <Stack direction="horizontal" gap={3}>
            <Button onClick={() => setOpen(false)} variant="ghost">
              Cancel
            </Button>
            <Button onClick={() => setOpen(false)}>Save</Button>
          </Stack>
        }
        description="Future artifact and settings modals will start from this primitive."
        onClose={() => setOpen(false)}
        open={open}
        title="Create study guide"
      >
        <Input label="Title" placeholder="Taxation and Business Law guide" />
      </Dialog>
    </SectionShell>
  );
}
