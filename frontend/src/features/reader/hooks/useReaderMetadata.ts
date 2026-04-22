import { signal, type Signal } from "@preact/signals";
import { useEffect, useRef } from "preact/hooks";

import type { DocumentDetail } from "@/services/api/endpoints";
import { documents } from "@/services/api/endpoints";

interface ReaderMetadataState {
  metadata: Signal<DocumentDetail | null>;
  loading: Signal<boolean>;
  error: Signal<Error | null>;
  refetch: () => Promise<void>;
}

export function useReaderMetadata(docId?: string): ReaderMetadataState {
  const docIdRef = useRef<string | undefined>(docId);
  docIdRef.current = docId;

  const stateRef = useRef<ReaderMetadataState | null>(null);
  if (!stateRef.current) {
    const metadata = signal<DocumentDetail | null>(null);
    const loading = signal(false);
    const error = signal<Error | null>(null);

    stateRef.current = {
      metadata,
      loading,
      error,
      refetch: async () => {
        const activeDocId = docIdRef.current;
        if (!activeDocId) {
          metadata.value = null;
          loading.value = false;
          error.value = null;
          return;
        }

        loading.value = true;
        error.value = null;
        try {
          metadata.value = await documents.detail(activeDocId);
        } catch (fetchError) {
          metadata.value = null;
          error.value = fetchError as Error;
        } finally {
          loading.value = false;
        }
      }
    };
  }

  useEffect(() => {
    void stateRef.current?.refetch();
  }, [docId]);

  return stateRef.current;
}
