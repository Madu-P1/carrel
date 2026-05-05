import { signal } from "@preact/signals";
import { useMemo, useRef } from "preact/hooks";

import type { TutorQueryRequest } from "@/services/api/endpoints";
import { tutor } from "@/services/api/endpoints";
import { companion } from "@/services/companion/bus";
import { normalizeGroundedAnswer } from "../types";
import type { GroundedAnswerEnvelope } from "../types";

type AskScope = Partial<
  Pick<TutorQueryRequest, "concept_id" | "confidence" | "doc_id" | "selected_text" | "subject_name">
>;

interface AskTutorState {
  answer: ReturnType<typeof signal<GroundedAnswerEnvelope | null>>;
  pending: ReturnType<typeof signal<boolean>>;
  error: ReturnType<typeof signal<Error | null>>;
  responseSerial: ReturnType<typeof signal<number>>;
  retry: () => Promise<void>;
  submit: (question: string, scope?: AskScope) => Promise<void>;
}

export function useAskTutor(): AskTutorState {
  const answer = useMemo(() => signal<GroundedAnswerEnvelope | null>(null), []);
  const pending = useMemo(() => signal(false), []);
  const error = useMemo(() => signal<Error | null>(null), []);
  const responseSerial = useMemo(() => signal(0), []);
  const lastPayload = useRef<TutorQueryRequest | null>(null);

  const run = async (payload: TutorQueryRequest) => {
    lastPayload.current = payload;
    pending.value = true;
    error.value = null;
    companion.thinkingStart();

    try {
      answer.value = normalizeGroundedAnswer(await tutor.ask(payload));
      responseSerial.value += 1;
    } catch (caught) {
      answer.value = null;
      error.value = caught as Error;
    } finally {
      pending.value = false;
      companion.thinkingEnd();
    }
  };

  return {
    answer,
    pending,
    error,
    responseSerial,
    submit: async (question, scope = {}) => {
      const trimmed = question.trim();
      if (!trimmed) {
        return;
      }

      await run({
        question: trimmed,
        response_mode: "standard",
        ...scope
      });
    },
    retry: async () => {
      if (!lastPayload.current) {
        return;
      }

      await run(lastPayload.current);
    }
  };
}
