import { useSignal } from "@preact/signals";

import { documents } from "@/services/api/endpoints";

export function useSetSubject() {
  const loading = useSignal(false);
  const error = useSignal<Error | null>(null);

  const setSubject = async (docIds: string[], subjectName: string) => {
    loading.value = true;
    error.value = null;
    try {
      for (const docId of docIds) {
        await documents.setSubject(docId, subjectName);
      }
    } catch (caught) {
      error.value = caught as Error;
      throw caught;
    } finally {
      loading.value = false;
    }
  };

  return { setSubject, loading, error };
}
