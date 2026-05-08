import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import { appShell, navigateTo } from "@/app/shell/useAppShell";
import { Badge, Button, Card, Divider, Icon, Stack, Text } from "@/design-system";
import {
  documents as documentsApi,
  study as studyApi,
  type DocumentRow,
  type SrsSubjectSummary
} from "@/services/api/endpoints";
import { events } from "@/services/metrics/events";
import { recordOnboardingStep } from "@/features/onboarding/FirstRunController";

import { ColdLoadIndicator } from "./components/ColdLoadIndicator";
import { AnswerSummary } from "./components/AnswerSummary";
import { AskCardList } from "./components/AskCardList";
import { ClaimList } from "./components/ClaimList";
import { FallbackAnswer } from "./components/FallbackAnswer";
import { QuestionInput } from "./components/QuestionInput";
import { ScopePill, type AskScopeValue } from "./components/ScopePill";
import { UnsupportedSpans } from "./components/UnsupportedSpans";
import { focusAskInput } from "./focusRegistry";
import { readAskQueryParams, scopeFromRoute } from "./askRoute";
import { useAskCards } from "./hooks/useAskCards";
import { useAskTutor } from "./hooks/useAskTutor";
import type { CitationRecord } from "./types";
import type { AskCard as AskCardData, AskCardsParams } from "@/services/api/endpoints";
import styles from "./AskView.module.css";

// Build-time flag — when "true", AskView swaps the synthesised-answer
// renderer for the typed-node card list. Keep the flag at the build
// boundary so production bundles pick exactly one path; runtime toggles
// would force every user to pay for both code paths in the bundle.
const CARDS_MODE = import.meta.env.VITE_RETRIEVAL_USE_NODES === "true";

// Subject-agnostic sample that demonstrates Carrel's strength
// (citation-grounded synthesis across whatever the user has imported)
// without assuming they have biology sources. Pre-rename this used to
// be a biology-specific question, which read as a mismatch in any
// finance / law / stats library.
const ASK_EMPTY_SAMPLE =
  "Summarise the main argument across my sources.";
const FIRST_ASK_EVENT_KEY = "carrel.metrics.first-ask-recorded";
const FIRST_GROUNDED_EVENT_KEY = "carrel.metrics.first-grounded-answer-recorded";

function AskEmptyState({ onPrimaryAction }: { onPrimaryAction: () => void }) {
  return (
    <Card className={styles.emptyStateCard} padding="md">
      <div className={styles.feedCardMeasure}>
        <Stack gap={3}>
          <Badge tone="info">Source-grounded</Badge>
          <h3 className={styles.emptyStateHeadline}>Ask a question about your sources</h3>
          <Text className={styles.emptyStateHelper}>
            Carrel retrieves supporting chunks first, then answers only with what those sources can actually support.
          </Text>
          <div>
            <Button
              leadingIcon={<Icon name="sparkle" size={14} />}
              onClick={onPrimaryAction}
              type="button"
            >
              Try a sample question
            </Button>
          </div>
        </Stack>
      </div>
    </Card>
  );
}

function AskErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <Card className={styles.errorCard} padding="lg">
      <Stack gap={3}>
        <Stack gap={1}>
          <Badge tone="danger">Request failed</Badge>
          <Text as="h2" variant="h2" weight="bold">
            Could not reach the tutor service
          </Text>
          <Text tone="secondary">{message}</Text>
        </Stack>
        <div>
          <Button onClick={onRetry} variant="secondary">
            Retry the question
          </Button>
        </div>
      </Stack>
    </Card>
  );
}

export function AskView() {
  const [question, setQuestion] = useState("");
  const { answer, error, pending, responseSerial, retry, submit } = useAskTutor();
  // Cards-mode hook always initialises but only fires when CARDS_MODE
  // is on. The pair-of-hooks shape keeps the AskView render branch
  // minimal at the cost of two unused signals when one mode is dead.
  const cards = useAskCards();
  const prefilledRef = useRef<string | null>(null);

  // Scope state. Default = Library (no filter). Persisted in the Thread
  // payload when the question is submitted; every answer surface downstream
  // can thus show which scope produced it.
  const [scope, setScope] = useState<AskScopeValue>({ kind: "library", readiness: "ready" });
  const [docs, setDocs] = useState<DocumentRow[]>([]);
  const [subjects, setSubjects] = useState<SrsSubjectSummary[]>([]);

  // Load documents + subjects on mount (and let refetch be cheap). We don't
  // poll — the picker opens rarely enough that stale-by-one-page is fine.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const [ds, ss] = await Promise.all([
          documentsApi.list(),
          studyApi.subjects(),
        ]);
        if (cancelled) return;
        setDocs(ds);
        setSubjects(ss.subjects);
      } catch {
        // Non-fatal — the pill falls back to Library-only if the lists fail.
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  // Pulls the scope state into the request payload. Keep the mapping in one
  // place so future scope kinds (Selection, Collection) slot in cleanly.
  const scopeToPayload = useCallback(
    (current: AskScopeValue) => {
      if (current.kind === "document" && current.docId) {
        return { doc_id: current.docId };
      }
      if (current.kind === "subject" && current.subjectName) {
        return { subject_name: current.subjectName };
      }
      return {};
    },
    []
  );

  // Cards endpoint uses camelCase params (frontend convention) vs the
  // tutor endpoint's snake_case. Single mapping to keep the render
  // branch tidy.
  const scopeToCardsParams = useCallback(
    (current: AskScopeValue): Partial<Omit<AskCardsParams, "q">> => {
      if (current.kind === "document" && current.docId) {
        return { docId: current.docId };
      }
      if (current.kind === "subject" && current.subjectName) {
        return { subjectName: current.subjectName };
      }
      return {};
    },
    []
  );

  const trackFirstAsk = useCallback((scopeKind: AskScopeValue["kind"] = scope.kind) => {
    try {
      if (window.localStorage.getItem(FIRST_ASK_EVENT_KEY) === "1") return;
      window.localStorage.setItem(FIRST_ASK_EVENT_KEY, "1");
    } catch {
      // If localStorage is unavailable, still record the coarse local event.
    }
    void events.track("ask.first_question", {
      scope_kind: scopeKind
    }, "ask");
  }, [scope.kind]);

  const trackScopedSubmit = useCallback((current: AskScopeValue) => {
    void events.track(
      "first_scoped_question_submitted",
      {
        scope_kind: current.kind,
        doc_id: current.kind === "document" ? current.docId ?? null : null,
        has_subject: current.kind === "subject"
      },
      "ask"
    );
    recordOnboardingStep({
      step: "asked_first_question",
      firstDocId: current.kind === "document" ? current.docId : undefined,
      firstQuestionSet: true
    });
  }, []);

  const handleSubmit = async () => {
    if (question.trim().length > 0) {
      trackFirstAsk();
      trackScopedSubmit(scope);
    }
    if (CARDS_MODE) {
      await cards.submit(question, scopeToCardsParams(scope));
    } else {
      await submit(question, scopeToPayload(scope));
    }
  };

  const focusQuestionInput = useCallback(() => {
    focusAskInput();
  }, []);

  // Consume ?q=…&auto=1 on mount. Guarded by prefilledRef so navigating
  // within Ask (or back-and-forth) doesn't re-fire the auto-submit.
  useEffect(() => {
    const params = readAskQueryParams(appShell.currentRoute.value);
    if (!params.question) return;
    if (prefilledRef.current === params.cacheKey) return;
    prefilledRef.current = params.cacheKey;
    const routeScope = scopeFromRoute(params, docs);
    setScope(routeScope);
    setQuestion(params.question);
    if (params.auto) {
      trackFirstAsk(routeScope.kind);
      trackScopedSubmit(routeScope);
      if (CARDS_MODE) {
        void cards.submit(params.question, scopeToCardsParams(routeScope));
      } else {
        void submit(params.question, scopeToPayload(routeScope));
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [docs, scopeToPayload, submit, trackFirstAsk, trackScopedSubmit]);

  useEffect(() => {
    if (scope.kind !== "document" || scope.docTitle || !scope.docId) return;
    const doc = docs.find((item) => item.id === scope.docId);
    if (!doc?.filename) return;
    setScope((current) =>
      current.kind === "document" && current.docId === scope.docId && !current.docTitle
        ? { ...current, docTitle: doc.filename ?? undefined }
        : current
    );
  }, [docs, scope]);

  const handleCitationClick = (citation: CitationRecord) => {
    void events.track(
      "first_citation_verified",
      {
        doc_id: citation.document_id,
        chunk_id: citation.chunk_id,
        page_num: citation.page_num ?? null
      },
      "reader"
    );
    recordOnboardingStep({
      step: "verified_first_citation",
      firstDocId: citation.document_id
    });
    navigateTo(
      `/reader/${encodeURIComponent(citation.document_id)}?chunk=${encodeURIComponent(citation.chunk_id)}`
    );
  };

  // Cards-mode counterpart to handleCitationClick. The reader pane
  // doesn't yet route on `?node=` (PR 4.2 wires that), so for now we
  // navigate page-level. The query param is sent so the reader can
  // pick it up once the route handler lands.
  const handleCardOpen = (card: AskCardData) => {
    void events.track(
      "first_citation_verified",
      {
        doc_id: card.doc_id,
        chunk_id: null,
        page_num: card.page ?? null,
      },
      "reader",
    );
    recordOnboardingStep({
      step: "verified_first_citation",
      firstDocId: card.doc_id,
    });
    const params = new URLSearchParams();
    params.set("node", String(card.node_id));
    if (card.page !== null && card.page !== undefined) {
      params.set("page", String(card.page));
    }
    navigateTo(`/reader/${encodeURIComponent(card.doc_id)}?${params.toString()}`);
  };

  const activeAnswer = answer.value;
  const claims = activeAnswer?.claims ?? [];
  const unsupportedSpans = activeAnswer?.unsupported_spans ?? [];
  const isGrounded = Boolean(activeAnswer?.grounded);
  const answerRevealKey = activeAnswer
    ? `answer-${responseSerial.value}`
    : "empty";

  // Cold-load heuristic state: track the most recent successful response
  // so ColdLoadIndicator can decide whether the current pending request
  // is likely a cold-start on the local model.
  const [lastSuccessAt, setLastSuccessAt] = useState<number | null>(null);
  const [lastProvider, setLastProvider] = useState<string | undefined>(undefined);
  useEffect(() => {
    if (activeAnswer && (activeAnswer.model ?? "").length > 0) {
      setLastSuccessAt(Date.now());
      setLastProvider(activeAnswer.model ?? undefined);
    }
  }, [activeAnswer, responseSerial.value]);

  useEffect(() => {
    if (!activeAnswer) return;
    try {
      if (window.localStorage.getItem(FIRST_GROUNDED_EVENT_KEY) === "1") return;
      window.localStorage.setItem(FIRST_GROUNDED_EVENT_KEY, "1");
    } catch {
      // Still record the local-only event when storage is unavailable.
    }
    void events.track(
      "first_grounded_answer_rendered",
      {
        grounded: Boolean(activeAnswer.grounded),
        citation_count: activeAnswer.citations.length,
        latency_ms: typeof activeAnswer.latency_ms === "number" ? activeAnswer.latency_ms : null
      },
      "ask"
    );
  }, [activeAnswer]);

  return (
    <div className={styles.wrap}>
      <Stack gap={6}>
        <Stack gap={3}>
          <span className={styles.viewEyebrow}>Live ask</span>
          <h1 className={styles.viewHeading}>
            Ask from your sources.
          </h1>
          <Text tone="secondary">
            Every claim shows the chunk it came from. Click a citation to
            jump into the Reader and verify the source for yourself.
          </Text>
        </Stack>

        <Card padding="lg">
          <Stack gap={5}>
            <Stack gap={2}>
              <div className={styles.scopeRow}>
                <ScopePill
                  documents={docs}
                  onChange={setScope}
                  subjects={subjects}
                  value={scope}
                />
                <Text tone="tertiary" variant="caption">
                  Retrieval is bounded to this scope. Every answer shows where it was grounded.
                </Text>
              </div>
              <QuestionInput
                disabled={CARDS_MODE ? cards.pending.value : pending.value}
                error={null}
                onSubmit={() => {
                  void handleSubmit();
                }}
                onValueChange={setQuestion}
                value={question}
              />
            </Stack>
            <Divider />

            {CARDS_MODE ? (
              <AskCardList
                response={cards.response.value}
                pending={cards.pending.value}
                error={cards.error.value}
                onOpen={handleCardOpen}
                onRetry={() => {
                  void cards.retry();
                }}
              />
            ) : null}

            {!CARDS_MODE && pending.value ? (
              <ColdLoadIndicator
                pending={pending.value}
                lastProvider={lastProvider}
                lastSuccessAt={lastSuccessAt}
              />
            ) : null}
            {!CARDS_MODE && !pending.value && error.value ? (
              <AskErrorState
                message={error.value.message}
                onRetry={() => {
                  void retry();
                }}
              />
            ) : null}
            {!CARDS_MODE && !pending.value && !error.value && !activeAnswer ? (
              <AskEmptyState
                onPrimaryAction={() => {
                  setQuestion(ASK_EMPTY_SAMPLE);
                  focusQuestionInput();
                }}
              />
            ) : null}
            {!CARDS_MODE && !pending.value && !error.value && activeAnswer ? (
              <Stack gap={3} key={answerRevealKey}>
                {isGrounded ? (
                  <AnswerSummary
                    cacheHit={Boolean(activeAnswer.cache_hit)}
                    citations={activeAnswer.citations}
                    latencyMs={activeAnswer.latency_ms ?? 0}
                    model={activeAnswer.model ?? ""}
                    onRetry={() => {
                      void retry();
                    }}
                    summary={activeAnswer.answer ?? ""}
                  />
                ) : null}
                {isGrounded ? (
                  <ClaimList claims={claims} onCitationClick={handleCitationClick} />
                ) : (
                  <FallbackAnswer
                    claims={claims}
                    error={activeAnswer.error ?? undefined}
                    onBroadenScope={() => {
                      setScope({ kind: "library", readiness: "ready" });
                    }}
                    onRephrase={() => {
                      focusQuestionInput();
                    }}
                    onRetry={() => {
                      void retry();
                    }}
                  />
                )}
                <UnsupportedSpans claimCount={claims.length} items={unsupportedSpans} />
              </Stack>
            ) : null}
          </Stack>
        </Card>
      </Stack>
    </div>
  );
}
