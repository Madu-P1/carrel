import { Icon, Stack } from "@/design-system";

import { SectionShell } from "./SectionShell";

const names = [
  "search",
  "plus",
  "x",
  "chevron-left",
  "chevron-right",
  "chevron-up",
  "chevron-down",
  "settings",
  "doc",
  "library",
  "ask",
  "study",
  "command",
  "sparkle"
] as const;

export function IconsSection() {
  return (
    <SectionShell description="Inline SVGs, no icon package yet." title="Icons">
      <Stack direction="horizontal" gap={3} wrap>
        {names.map((name) => (
          <Icon key={name} name={name} size={18} title={name} />
        ))}
      </Stack>
    </SectionShell>
  );
}
