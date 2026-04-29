import { Badge, Stack, Text, toast } from "@/design-system";

import { copyAskCardText, saveAskAnchorDraft } from "../anchorDrafts";
import { friendlyErrorFor } from "../errorMessages";
import type { ClaimRecord } from "../types";
import styles from "../AskView.module.css";
import { AnswerFeedCard, type AnswerFeedAction } from "./AnswerFeedCard";

interface FallbackAnswerProps {
  claims: ClaimRecord[];
  error?: string;
  /** Invoked when the user clicks "Broaden to Library". Sets scope back
   *  to library-wide. Not bound for non-weak-coverage errors. */
  onBroadenScope?: () => void;
  /** Invoked when the user clicks "Rephrase question". Typically focuses
   *  the question input. Not bound for non-weak-coverage errors. */
  onRephrase?: () => void;
  /** Invoked when the user clicks "Retry". Re-runs the most recent Ask payload. */
  onRetry?: () => void;
}

function normalizedText(value: string): string {
  return value.replace(/[^a-z0-9\s]/gi, "").replace(/\s+/g, " ").trim().toLowerCase();
}

function fallbackSupportText(claim: ClaimRecord): string {
  const candidate = (claim.citations[0]?.snippet ?? claim.citations[0]?.content ?? "").trim();
  if (candidate && normalizedText(candidate) !== normalizedText(claim.text)) {
    return candidate;
  }
  const citation = claim.citations[0];
  if (citation?.document_name) {
    return `Nearest retrieved passage from ${citation.document_name}${citation.page_num ? ` on page ${citation.page_num}` : ""}.`;
  }
  return "Nearest retrieved passage from your current scope.";
}

function fallbackLocations(claim: ClaimRecord): string[] {
  return claim.citations.map((citation) =>
    [
      citation.document_name ?? citation.document_id ?? "Source",
      citation.page_num ? `p.${citation.page_num}` : null,
      citation.chunk_id ? `chunk ${citation.chunk_id}` : null
    ]
      .filter(Boolean)
      .join(" · ")
  );
}

/**
 * FallbackAnswer renders the UI when the tutor didn't return a grounded
 * answer. The shape branches on error:
 *
 *   weak_coverage: deliberate refusal. Claude was NOT called; we refused
 *     because scope fallback thinned the evidence. Shows a refusal card
 *     with recovery actions + the nearest passages we did find.
 *
 *   everything else: legacy fallback shape. AI synthesis was attempted but
 *     failed (API error, disabled, etc). Shows the raw passages so the
 *     user can still work from the source.
 *
 * Both shapes share the passages list so the user always walks away with
 * something readable.
 */
export function FallbackAnswer({
  claims,
  error,
  onBroadenScope,
  onRephrase,
  onRetry
}: FallbackAnswerProps) {
  const friendly = friendlyErrorFor(error);
  const isRefusal = error === "weak_coverage";
  const summaryActions: AnswerFeedAction[] = [];

  if (onRetry) {
    summaryActions.push({
      label: "Retry the question",
      onClick: () => {
        onRetry();
      }
    });
  }
  if (isRefusal && onBroadenScope) {
    summaryActions.push({
      label: "Broaden to Library",
      onClick: () => {
        onBroadenScope();
      }
    });
  }
  if (isRefusal && onRephrase) {
    summaryActions.push({
      label: "Rephrase question",
      onClick: () => {
        onRephrase();
      }
    });
  }

  return (
    <section className={styles.fallbackWrap}>
      <Stack gap={3}>
        <AnswerFeedCard
          actions={summaryActions}
          body={
            isRefusal
              ? "The evidence in your current scope did not cleanly answer the question, so I stopped short instead of inventing a summary."
              : "Showing the closest retrieved passages so you can still work directly from the source."
          }
          evidence={
            <Stack gap={1}>
              {friendly ? <Text className={styles.feedCardMetaText}>{friendly.title}</Text> : null}
              {friendly?.action ? <Text className={styles.feedCardMetaText}>{friendly.action}</Text> : null}
              {friendly ? (
                <Text className={[styles.feedCardMetaText, styles.feedCardLocation].join(" ")}>
                  code: {friendly.code}
                </Text>
              ) : null}
            </Stack>
          }
          eyebrow={
            <Badge tone={isRefusal ? "info" : "warning"}>
              {isRefusal ? "Grounded refusal" : "Fallback"}
            </Badge>
          }
          title={isRefusal ? "I refused this one." : "Couldn't synthesize an answer."}
        />

        {claims.length > 0 ? (
          <Stack gap={2}>
            {isRefusal ? (
              <Text tone="tertiary" variant="caption">
                Nearest passages I did find, in case they help:
              </Text>
            ) : null}
            <div className={styles.claimList}>
              {claims.map((claim, index) => (
                <AnswerFeedCard
                  actions={[
                    {
                      label: "Copy",
                      onClick: () => {
                        void copyAskCardText(claim.text)
                          .then(() => {
                            toast.success("Copied passage", "The fallback passage is on your clipboard.");
                          })
                          .catch(() => {
                            toast.error("Copy failed", "Clipboard access is unavailable in this context.");
                          });
                      }
                    },
                    {
                      label: "Save as anchor",
                      onClick: () => {
                        try {
                          const saved = saveAskAnchorDraft({
                            title: claim.text,
                            body: fallbackSupportText(claim),
                            sourceKind: "fallback-passage",
                            citation: claim.citations[0]
                          });
                          toast.success(
                            saved.status === "created" ? "Anchor saved" : "Anchor refreshed",
                            claim.citations[0]?.document_name ?? "Saved from this fallback passage."
                          );
                        } catch {
                          toast.error("Save failed", "Could not write this anchor draft locally.");
                        }
                      }
                    }
                  ]}
                  body={fallbackSupportText(claim)}
                  delayMs={120 + index * 60}
                  evidence={
                    <div className={styles.feedCardLocationList}>
                      {fallbackLocations(claim).map((location) => (
                        <span className={styles.feedCardLocation} key={`${claim.text}-${location}`}>
                          {location}
                        </span>
                      ))}
                    </div>
                  }
                  key={claim.text}
                  title={claim.text}
                />
              ))}
            </div>
          </Stack>
        ) : null}
      </Stack>
    </section>
  );
}
