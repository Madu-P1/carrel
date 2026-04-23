import { Badge, Button, Icon, Stack, Text } from "@/design-system";

import { renderMarkdown } from "@/lib/markdown";
import type { ClaimRecord } from "../types";
import { friendlyErrorFor } from "../errorMessages";
import styles from "../AskView.module.css";

interface FallbackAnswerProps {
  claims: ClaimRecord[];
  error?: string;
  /** Invoked when the user clicks "Broaden to Library". Sets scope back
   *  to library-wide. Not bound for non-weak-coverage errors. */
  onBroadenScope?: () => void;
  /** Invoked when the user clicks "Rephrase question". Typically focuses
   *  the question input. Not bound for non-weak-coverage errors. */
  onRephrase?: () => void;
}

/**
 * FallbackAnswer renders the UI when the tutor didn't return a grounded
 * answer. The shape branches on error:
 *
 *   weak_coverage: deliberate refusal. Claude was NOT called; we refused
 *     because scope fallback thinned the evidence. Shows a refusal card
 *     with 3 recovery actions + the nearest passages we did find.
 *
 *   everything else: legacy fallback shape. AI synthesis was attempted but
 *     failed (API error, disabled, etc). Shows the raw passages so the
 *     user can still work from the source.
 *
 * Both shapes share the passages list so the user always walks away with
 * something readable.
 */
export function FallbackAnswer({ claims, error, onBroadenScope, onRephrase }: FallbackAnswerProps) {
  const friendly = friendlyErrorFor(error);
  const isRefusal = error === "weak_coverage";
  return (
    <section className={styles.fallbackWrap}>
      <Stack gap={3}>
        <Stack gap={1}>
          <Badge tone={isRefusal ? "info" : "warning"}>
            {isRefusal ? "Grounded refusal" : "Fallback"}
          </Badge>
          <Text as="h2" variant="h2" weight="bold">
            {isRefusal ? "I refused this one." : "AI synthesis unavailable"}
          </Text>
          {friendly ? <Text tone="secondary">{friendly.title}</Text> : null}
          <Text tone="secondary">
            {isRefusal
              ? "The evidence in your current scope didn't cleanly match the question. I wouldn't make up an answer from passages that weren't actually a match."
              : "Showing raw retrieved passages so you can still work from the source."}
          </Text>
          {friendly?.action ? <Text tone="secondary">{friendly.action}</Text> : null}
          {friendly ? (
            <Text tone="tertiary" variant="caption">
              code: {friendly.code}
            </Text>
          ) : null}
        </Stack>
        {isRefusal ? (
          <Stack direction="horizontal" gap={2} wrap>
            {onBroadenScope ? (
              <Button
                leadingIcon={<Icon name="library" size={14} />}
                onClick={onBroadenScope}
                variant="secondary"
              >
                Broaden to Library
              </Button>
            ) : null}
            {onRephrase ? (
              <Button
                leadingIcon={<Icon name="ask" size={14} />}
                onClick={onRephrase}
                variant="secondary"
              >
                Rephrase question
              </Button>
            ) : null}
          </Stack>
        ) : null}
        {claims.length > 0 ? (
          <Stack gap={2}>
            {isRefusal ? (
              <Text tone="tertiary" variant="caption">
                Nearest passages I did find, in case they help:
              </Text>
            ) : null}
            <ol className={styles.fallbackClaims}>
              {claims.map((claim) => (
                <li key={claim.text}>
                  <div className={styles.prose}>{renderMarkdown(claim.text)}</div>
                </li>
              ))}
            </ol>
          </Stack>
        ) : null}
      </Stack>
    </section>
  );
}
