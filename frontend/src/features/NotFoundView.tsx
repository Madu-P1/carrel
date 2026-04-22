import { Badge, Card, Stack, Text } from "@/design-system";

export function NotFoundView() {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <Badge tone="danger">Route not found</Badge>
        <Text as="h2" variant="h1" weight="bold">
          This workspace page does not exist yet.
        </Text>
        <Text tone="secondary">
          Use the Navigate menu or the sidebar to return to a supported surface.
        </Text>
      </Stack>
    </Card>
  );
}
