import { events } from "@/services/metrics/events";

export type OnboardingStep =
  | "empty_library"
  | "importing_first_source"
  | "source_ready"
  | "asked_first_question"
  | "verified_first_citation"
  | "created_first_card"
  | "scheduled_first_block";

export interface OnboardingState {
  step: OnboardingStep;
  firstDocId?: string;
  firstQuestionSet?: boolean;
  completedAt?: string;
}

const ONBOARDING_STATE_KEY = "carrel.onboarding";

export function loadOnboardingState(): OnboardingState {
  try {
    const raw = window.localStorage.getItem(ONBOARDING_STATE_KEY);
    if (!raw) return { step: "empty_library" };
    const parsed = JSON.parse(raw) as Partial<OnboardingState>;
    return {
      step: isOnboardingStep(parsed.step) ? parsed.step : "empty_library",
      firstDocId: typeof parsed.firstDocId === "string" ? parsed.firstDocId : undefined,
      firstQuestionSet: typeof parsed.firstQuestionSet === "boolean" ? parsed.firstQuestionSet : undefined,
      completedAt: typeof parsed.completedAt === "string" ? parsed.completedAt : undefined
    };
  } catch {
    return { step: "empty_library" };
  }
}

export function recordOnboardingStep(patch: Partial<OnboardingState>): OnboardingState {
  const current = loadOnboardingState();
  const next = { ...current, ...patch };
  try {
    window.localStorage.setItem(ONBOARDING_STATE_KEY, JSON.stringify(next));
  } catch {
    // In-memory flow still proceeds; local metrics are best-effort.
  }
  void events.track(
    "onboarding.step",
    {
      step: next.step,
      has_doc: Boolean(next.firstDocId),
      first_question_set: Boolean(next.firstQuestionSet),
      completed: Boolean(next.completedAt)
    },
    "onboarding"
  );
  return next;
}

function isOnboardingStep(value: unknown): value is OnboardingStep {
  return (
    value === "empty_library" ||
    value === "importing_first_source" ||
    value === "source_ready" ||
    value === "asked_first_question" ||
    value === "verified_first_citation" ||
    value === "created_first_card" ||
    value === "scheduled_first_block"
  );
}
