import { signal } from "@preact/signals";
import type { Signal } from "@preact/signals";
import { useMemo, useRef } from "preact/hooks";

import { ask } from "@/services/api/endpoints";
import type { AskCardsParams, AskCardsResponse } from "@/services/api/endpoints";

interface AskCardsState {
  response: Signal<AskCardsResponse | null>;
  pending: Signal<boolean>;
  error: Signal<Error | null>;
  responseSerial: Signal<number>;
  retry: () => Promise<void>;
  submit: (
    question: string,
    scope?: Partial<Omit<AskCardsParams, "q">>,
  ) => Promise<void>;
}

/**
 * Free-tier Ask hook — pulls citation-ready cards from the typed-node
 * retrieval path (`/api/ask/cards`). Mirrors the `useAskTutor` shape so
 * the AskView can switch between paths with minimal branching.
 *
 * No synthesis runs here. Cards are the answer. The retry/submit
 * surface preserves the last params so error states have a meaningful
 * "try again" button.
 */
export function useAskCards(): AskCardsState {
  const response = useMemo(() => signal<AskCardsResponse | null>(null), []);
  const pending = useMemo(() => signal(false), []);
  const error = useMemo(() => signal<Error | null>(null), []);
  const responseSerial = useMemo(() => signal(0), []);
  const lastParams = useRef<AskCardsParams | null>(null);

  const run = async (params: AskCardsParams) => {
    lastParams.current = params;
    pending.value = true;
    error.value = null;

    try {
      response.value = await ask.cards(params);
      responseSerial.value += 1;
    } catch (caught) {
      response.value = null;
      error.value = caught as Error;
    } finally {
      pending.value = false;
    }
  };

  return {
    response,
    pending,
    error,
    responseSerial,
    submit: async (question, scope = {}) => {
      const trimmed = question.trim();
      if (!trimmed) {
        return;
      }
      await run({ q: trimmed, ...scope });
    },
    retry: async () => {
      if (!lastParams.current) {
        return;
      }
      await run(lastParams.current);
    },
  };
}
