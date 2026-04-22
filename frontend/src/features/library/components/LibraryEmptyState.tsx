import { Badge, Card, Icon, Stack, Text } from "@/design-system";

export function LibraryEmptyState() {
  return (
    <Card padding="lg">
      <Stack gap={3}>
        <Badge tone="info">Empty library</Badge>
        <Text as="h2" variant="h1" weight="bold">
          No sources yet.
        </Text>
        <Text tone="secondary">
          Drop a file into the import zone or press ⌘I to bring your first source into Einstein.
        </Text>
        <Stack direction="horizontal" gap={2}>
          <Icon name="doc" />
          <Text tone="tertiary">PDF, DOCX, slides, text, and more are supported.</Text>
        </Stack>
      </Stack>
    </Card>
  );
}
