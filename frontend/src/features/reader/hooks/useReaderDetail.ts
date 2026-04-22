import { useEffect } from "preact/hooks";

import { createQuery } from "@/lib/query";
import type { DocumentDetail } from "@/services/api/endpoints";
import { documents } from "@/services/api/endpoints";

const detailQueryCache = new Map<string, ReturnType<typeof createQuery<DocumentDetail>>>();
const initializedDocIds = new Set<string>();

function ensureDetailQuery(docId: string) {
  let query = detailQueryCache.get(docId);
  if (!query) {
    query = createQuery(() => documents.detail(docId));
    detailQueryCache.set(docId, query);
  }
  return query;
}

export function useReaderDetail(docId: string) {
  const query = ensureDetailQuery(docId);

  useEffect(() => {
    const unsubscribe = query.subscribe();
    if (
      !initializedDocIds.has(docId) &&
      query.data.value === undefined &&
      query.error.value === null &&
      !query.loading.value
    ) {
      initializedDocIds.add(docId);
      void query.refetch();
    }
    return unsubscribe;
  }, [docId, query]);

  return query;
}

export function resetReaderDetailQueries() {
  initializedDocIds.clear();
  for (const query of detailQueryCache.values()) {
    query.reset();
  }
  detailQueryCache.clear();
}

export function invalidateReaderDetailQuery(docId: string) {
  const query = detailQueryCache.get(docId);
  initializedDocIds.delete(docId);
  if (query) {
    query.reset();
    detailQueryCache.delete(docId);
  }
}
