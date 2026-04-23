import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";
import { dispatchMenuCommand } from "@/services/native/menu";

export function LibraryEmptyState() {
  return (
    <Card padding="lg">
      <Stack gap={4}>
        <Stack gap={3}>
          <Badge tone="info">Empty library</Badge>
          <Text as="h2" variant="h1" weight="bold">
            No sources yet.
          </Text>
          <Text tone="secondary">
            Drop a file onto the import zone above, or click Import to pick from your Mac.
          </Text>
          <Stack direction="horizontal" gap={2}>
            <Icon name="doc" />
            <Text tone="tertiary">PDF, DOCX, slides, text, and more are supported.</Text>
          </Stack>
        </Stack>
        <Stack direction="horizontal" gap={2}>
          <Button
            keyHint="⌘I"
            leadingIcon={<Icon name="plus" />}
            onClick={() => dispatchMenuCommand("file.import")}
          >
            Import a source
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}
