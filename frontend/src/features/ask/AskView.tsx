import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import { appShell, navigateTo } from "@/app/shell/useAppShell";
import { Badge, Button, Card, Divider, Icon, Stack, Text } from "@/design-system";
import {
  documents as documentsApi,
  study as studyApi,
  type DocumentRow,
  type SrsSubjectSummary
} from "@/services/api/endpoints";

import { ColdLoadIndicator } from "./components/ColdLoadIndicator";
import { AnswerSummary } from "./components/AnswerSummary";
import { ClaimList } from "./components/ClaimList";
import { FallbackAnswer } from "./components/FallbackAnswer";
import { QuestionInput } from "./components/QuestionInput";
import { ScopePill, type AskScopeValue } from "./components/ScopePill";
import { UnsupportedSpans } from "./components/UnsupportedSpans";
import { useAskTutor } from "./hooks/useAskTutor";
import type { CitationRecord } from "./types";
import styles from "./AskView.module.css";

const ASK_EMPTY_SAMPLE = "What do my sources say about mitosis checkpoints?";

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

/**
 * Parse `?q=<question>&auto=1` from the current route. Used when the
 * Dashboard's Hero Ask prompt routes into this view with a pre-filled
 * question — the auto flag tells us to kick off retrieval immediately
 * without the user having to press Enter a second time.
 */
function readAskQueryParams(rawPath: string): { question: string | null; auto: boolean } {
  try {
    const url = new URL(rawPath || "/ask", "https://carrel.local");
    const q = url.searchParams.get("q");
    const auto = url.searchParams.get("auto");
    return {
      question: q && q.trim().length > 0 ? q : null,
      auto: auto === "1" || auto === "true"
    };
  } catch {
    return { question: null, auto: false };
  }
}

export function AskView() {
  const [question, setQuestion] = useState("");
  const { answer, error, pending, responseSerial, retry, submit } = useAskTutor();
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

  const handleSubmit = async () => {
    await submit(question, scopeToPayload(scope));
  };

  const focusQuestionInput = useCallback(() => {
    const field = document.querySelector(
      "input[placeholder*='source say' i]"
    ) as HTMLInputElement | null;
    field?.focus();
  }, []);

  // Consume ?q=…&auto=1 on mount. Guarded by prefilledRef so navigating
  // within Ask (or back-and-forth) doesn't re-fire the auto-submit.
  useEffect(() => {
    const params = readAskQueryParams(appShell.currentRoute.value);
    if (!params.question) return;
    if (prefilledRef.current === params.question) return;
    prefilledRef.current = params.question;
    setQuestion(params.question);
    if (params.auto) {
      void submit(params.question);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleCitationClick = (citation: CitationRecord) => {
    navigateTo(
      `/reader/${encodeURIComponent(citation.document_id)}?chunk=${encodeURIComponent(citation.chunk_id)}`
    );
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
                disabled={pending.value}
                error={null}
                onSubmit={() => {
                  void handleSubmit();
                }}
                onValueChange={setQuestion}
                value={question}
              />
            </Stack>
            <Divider />

            {pending.value ? (
              <ColdLoadIndicator
                pending={pending.value}
                lastProvider={lastProvider}
                lastSuccessAt={lastSuccessAt}
              />
            ) : null}
            {!pending.value && error.value ? (
              <AskErrorState
                message={error.value.message}
                onRetry={() => {
                  void retry();
                }}
              />
            ) : null}
            {!pending.value && !error.value && !activeAnswer ? (
              <AskEmptyState
                onPrimaryAction={() => {
                  setQuestion(ASK_EMPTY_SAMPLE);
                  focusQuestionInput();
                }}
              />
            ) : null}
            {!pending.value && !error.value && activeAnswer ? (
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
