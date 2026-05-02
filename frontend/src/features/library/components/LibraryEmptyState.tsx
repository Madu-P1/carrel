import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";
import { toast } from "@/design-system";
import { onboarding } from "@/services/api/endpoints";
import { events } from "@/services/metrics/events";
import { dispatchMenuCommand } from "@/services/native/menu";

interface LibraryEmptyStateProps {
  onDemoLoaded?: () => void;
}

export function LibraryEmptyState({ onDemoLoaded }: LibraryEmptyStateProps) {
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
          <Button
            leadingIcon={<Icon name="library" />}
            variant="secondary"
            onClick={() => {
              void onboarding.seedDemoLibrary()
                .then((result) => {
                  if (result.seeded) {
                    void events.track("onboarding.demo_library_loaded", { force: false }, "library");
                    toast.success("Demo library loaded", "Open a sample source to inspect evidence and create anchors.");
                    onDemoLoaded?.();
                  } else {
                    toast.info("Demo library skipped", "Your library already has sources.");
                  }
                })
                .catch(() => {
                  toast.error("Demo load failed", "Carrel could not create the sample library.");
                });
            }}
          >
            Load sample library
          </Button>
        </Stack>
      </Stack>
    </Card>
  );
}
