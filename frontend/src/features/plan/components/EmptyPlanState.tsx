import { useState } from "preact/hooks";

import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";

import { AddDeadlineDialog } from "./AddDeadlineDialog";

interface EmptyPlanStateProps {
  onAddFeed: () => void;
}

/**
 * Empty state for /plan with zero feeds connected.
 *
 * Per the student/deadline thesis (the wedge is "the deadline is the
 * unit of work"), the primary CTA is "Add a deadline" — students can
 * start using the coach immediately without calendar setup. Connecting
 * a calendar is the secondary CTA: it's how the suggestions land in
 * real free blocks instead of being abstract.
 *
 * Voice-rule compliant: scripted copy, two clear CTAs, no AI flavor.
 */
export function EmptyPlanState({ onAddFeed }: EmptyPlanStateProps) {
  const [addDeadlineOpen, setAddDeadlineOpen] = useState(false);

  return (
    <>
      <Card padding="lg">
        <Stack gap={4}>
          <Stack gap={3}>
            <Badge tone="info">Plan</Badge>
            <Text as="h2" variant="h1" weight="bold">
              Start with what's due on Friday.
            </Text>
            <Text tone="secondary">
              Add the deadline that's stressing you out. The coach starts
              scheduling study time toward it immediately — and connecting
              your calendar later lets the suggestions land in your real
              free blocks.
            </Text>
            <Stack direction="horizontal" gap={2}>
              <Icon name="library" size={14} />
              <Text tone="tertiary">
                Calendar feeds work with Google, Apple, Outlook, and
                ESCP Blackboard's per-user iCal export. Auth tokens are
                never stored — feed URLs are revocable from your provider.
              </Text>
            </Stack>
          </Stack>
          <Stack direction="horizontal" gap={2}>
            <Button
              leadingIcon={<Icon name="plus" />}
              onClick={() => setAddDeadlineOpen(true)}
            >
              Add a deadline
            </Button>
            <Button
              keyHint="⌘N"
              leadingIcon={<Icon name="library" />}
              onClick={onAddFeed}
              variant="secondary"
            >
              Connect a calendar
            </Button>
          </Stack>
        </Stack>
      </Card>
      <AddDeadlineDialog
        open={addDeadlineOpen}
        onClose={() => setAddDeadlineOpen(false)}
        onAdded={() => undefined}
      />
    </>
  );
}
