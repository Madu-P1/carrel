import { Button, Dialog, Stack, Text } from "@/design-system";

interface DeleteConfirmDialogProps {
  documentName: string;
  error: Error | null;
  loading: boolean;
  onClose: () => void;
  onConfirm: () => void;
  open: boolean;
}

export function DeleteConfirmDialog({
  documentName,
  error,
  loading,
  onClose,
  onConfirm,
  open
}: DeleteConfirmDialogProps) {
  return (
    <Dialog
      actions={
        <Stack direction="horizontal" gap={2}>
          <Button onClick={onClose} variant="ghost">
            Cancel
          </Button>
          <Button isLoading={loading} onClick={onConfirm} variant="danger">
            Delete source
          </Button>
        </Stack>
      }
      description="This removes the source and its generated study items from the workspace."
      onClose={onClose}
      open={open}
      title={`Delete ${documentName}?`}
    >
      <Stack gap={2}>
        <Text>
          This action deletes the document record, derived study artifacts, and local source file.
        </Text>
        {error ? <Text tone="danger">{error.message}</Text> : null}
      </Stack>
    </Dialog>
  );
}
