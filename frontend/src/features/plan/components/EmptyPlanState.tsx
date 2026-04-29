import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";

interface EmptyPlanStateProps {
  onAddFeed: () => void;
}

/**
 * Empty state for /plan with zero feeds connected. Voice-rule
 * compliant: scripted copy, single Button CTA, no AI flavor.
 *
 * The headline names the value the user gets ("see your week"), not
 * the mechanism ("add an iCal URL"). The helper line tells them
 * which providers we know work.
 */
export function EmptyPlanState({ onAddFeed }: EmptyPlanStateProps) {
  return (
    <Card padding="lg">
      <Stack gap={4}>
        <Stack gap={3}>
          <Badge tone="info">Plan</Badge>
          <Text as="h2" variant="h1" weight="bold">
            See your week and where to study.
          </Text>
          <Text tone="secondary">
            Connect a calendar to ground the coach in your real schedule.
            Works with Google Calendar, Apple Calendar, Outlook, and
            ESCP Blackboard's per-user iCal export.
          </Text>
          <Stack direction="horizontal" gap={2}>
            <Icon name="library" size={14} />
            <Text tone="tertiary">
              We never store your auth tokens — feed URLs are revocable
              from your calendar provider.
            </Text>
          </Stack>
        </Stack>
        <Stack direction="horizontal" gap={2}>
          <Button
            keyHint="⌘N"
            leadingIcon={<Icon name="plus" />}
            onClick={onAddFeed}
          >
            Connect a calendar
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}
