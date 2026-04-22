import { batch, signal } from "@preact/signals";
import { useEffect, useMemo } from "preact/hooks";

export interface Query<T> {
  data: ReturnType<typeof signal<T | undefined>>;
  loading: ReturnType<typeof signal<boolean>>;
  error: ReturnType<typeof signal<Error | null>>;
  refetch: () => Promise<void>;
  reset: () => void;
  subscribe: () => () => void;
}

export function createQuery<T>(fetcher: () => Promise<T>): Query<T> {
  const data = signal<T | undefined>(undefined);
  const loading = signal(false);
  const error = signal<Error | null>(null);
  let activeSubscribers = 0;
  let generation = 0;

  const subscribe = () => {
    activeSubscribers += 1;
    return () => {
      activeSubscribers = Math.max(0, activeSubscribers - 1);
      if (activeSubscribers === 0) {
        generation += 1;
      }
    };
  };

  const reset = () => {
    generation += 1;
    batch(() => {
      data.value = undefined;
      loading.value = false;
      error.value = null;
    });
  };

  const refetch = async () => {
    const requestGeneration = generation + 1;
    generation = requestGeneration;
    batch(() => {
      loading.value = true;
      error.value = null;
    });
    try {
      const result = await fetcher();
      if (requestGeneration !== generation || activeSubscribers === 0) {
        return;
      }
      batch(() => {
        data.value = result;
        loading.value = false;
      });
    } catch (caught) {
      if (requestGeneration !== generation || activeSubscribers === 0) {
        return;
      }
      batch(() => {
        error.value = caught as Error;
        loading.value = false;
      });
    }
  };

  return { data, loading, error, refetch, reset, subscribe };
}

export function useQuery<T>(fetcher: () => Promise<T>): Query<T> {
  const query = useMemo(() => createQuery(fetcher), [fetcher]);

  useEffect(() => {
    const unsubscribe = query.subscribe();
    void query.refetch();
    return unsubscribe;
  }, [query]);

  return query;
}
