import { useSignal } from "@preact/signals";

import { documents } from "@/services/api/endpoints";
import { invalidateReaderDetailQuery } from "@/features/reader/hooks/useReaderDetail";

export function useDeleteDocument() {
  const loading = useSignal(false);
  const error = useSignal<Error | null>(null);

  const deleteDocument = async (docId: string) => {
    loading.value = true;
    error.value = null;
    try {
      await documents.delete(docId);
      invalidateReaderDetailQuery(docId);
    } catch (caught) {
      error.value = caught as Error;
      throw caught;
    } finally {
      loading.value = false;
    }
  };

  return { deleteDocument, loading, error };
}
