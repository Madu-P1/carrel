import { useEffect, useRef, useState } from "preact/hooks";

import { appShell, navigateTo } from "@/app/shell/useAppShell";
import { Badge, Button, Card, Divider, Stack, Text } from "@/design-system";

import { AnswerMetaBar } from "./components/AnswerMetaBar";
import { ColdLoadIndicator } from "./components/ColdLoadIndicator";
import { AnswerSummary } from "./components/AnswerSummary";
import { ClaimList } from "./components/ClaimList";
import { FallbackAnswer } from "./components/FallbackAnswer";
import { QuestionInput } from "./components/QuestionInput";
import { UnsupportedSpans } from "./components/UnsupportedSpans";
import { useAskTutor } from "./hooks/useAskTutor";
import type { CitationRecord } from "./types";
import styles from "./AskView.module.css";

function AskEmptyState() {
  return (
    <Card padding="lg">
      <Stack gap={4}>
        <Stack gap={3}>
          <Badge tone="info">Source-grounded</Badge>
          <Text as="h2" variant="h1" weight="bold">
            Ask a question about your sources
          </Text>
          <Text tone="secondary">
            Einstein will retrieve relevant chunks, synthesize only what those sources support,
            and keep unsupported claims visibly separate.
          </Text>
        </Stack>
        <Stack gap={2}>
          <Text tone="tertiary" variant="caption">
            Try one to get started:
          </Text>
          <Stack gap={1}>
            {[
              "What do my sources say about...?",
              "Compare the key arguments between...",
              "What is the mechanism behind...?"
            ].map((prompt) => (
              <Text key={prompt} tone="secondary">
                <span style={{ color: "var(--color-accent)" }}>›</span> {prompt}
              </Text>
            ))}
          </Stack>
        </Stack>
      </Stack>
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
            Einstein could not reach the tutor service
          </Text>
          <Text tone="secondary">{message}</Text>
        </Stack>
        <div>
          <Button onClick={onRetry} variant="secondary">
            Retry
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
    const url = new URL(rawPath || "/ask", "https://einstein.local");
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

  const handleSubmit = async () => {
    await submit(question);
  };

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
          <Badge tone="info">Live Ask</Badge>
          <h2 className={styles.viewHeading}>
            Ask Einstein from your actual source library.
          </h2>
          <Text tone="secondary">
            Citation chips jump straight into the Reader so you can inspect the supporting chunk
            instead of trusting the summary blindly.
          </Text>
        </Stack>

        <Card padding="lg">
          <Stack gap={5}>
            <QuestionInput
              disabled={pending.value}
              error={null}
              onSubmit={() => {
                void handleSubmit();
              }}
              onValueChange={setQuestion}
              value={question}
            />
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
            {!pending.value && !error.value && !activeAnswer ? <AskEmptyState /> : null}
            {!pending.value && !error.value && activeAnswer ? (
              <Stack gap={5} key={answerRevealKey}>
                {isGrounded ? <AnswerSummary summary={activeAnswer.answer ?? ""} /> : null}
                {isGrounded ? (
                  <ClaimList claims={claims} onCitationClick={handleCitationClick} />
                ) : (
                  <FallbackAnswer claims={claims} error={activeAnswer.error ?? undefined} />
                )}
                <UnsupportedSpans claimCount={claims.length} items={unsupportedSpans} />
                <AnswerMetaBar
                  cacheHit={Boolean(activeAnswer.cache_hit)}
                  latencyMs={activeAnswer.latency_ms ?? 0}
                  model={activeAnswer.model ?? ""}
                />
              </Stack>
            ) : null}
          </Stack>
        </Card>
      </Stack>
    </div>
  );
}
