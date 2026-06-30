import { Button, Card, Icon, Stack, Text } from "@/design-system";

interface LibraryErrorStateProps {
  error: Error;
  onRetry: () => void;
}

export function LibraryErrorState({ error, onRetry }: LibraryErrorStateProps) {
  return (
    <Card data-testid="library-error" role="alert" padding="lg">
      <Stack gap={3}>
        <Text as="h2" tone="danger" variant="h2" weight="bold">
          Library failed to load
        </Text>
        <Text tone="secondary">{error.message}</Text>
        <Button leadingIcon={<Icon name="sparkle" />} onClick={onRetry} variant="secondary">
          Retry
        </Button>
      </Stack>
    </Card>
  );
}
