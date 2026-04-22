import { Badge, Stack, Text } from "@/design-system";

import type { ClaimRecord } from "../types";
import { friendlyErrorFor } from "../errorMessages";
import styles from "../AskView.module.css";

interface FallbackAnswerProps {
  claims: ClaimRecord[];
  error?: string;
}

export function FallbackAnswer({ claims, error }: FallbackAnswerProps) {
  const friendly = friendlyErrorFor(error);
  return (
    <section className={styles.fallbackWrap}>
      <Stack gap={3}>
        <Stack gap={1}>
          <Badge tone="warning">Fallback</Badge>
          <Text as="h2" variant="h2" weight="bold">
            AI synthesis unavailable
          </Text>
          {friendly ? <Text tone="secondary">{friendly.title}</Text> : null}
          <Text tone="secondary">
            Showing raw retrieved passages so you can still work from the source.
          </Text>
          {friendly?.action ? <Text tone="secondary">{friendly.action}</Text> : null}
          {friendly ? (
            <Text tone="tertiary" variant="caption">
              code: {friendly.code}
            </Text>
          ) : null}
        </Stack>
        <ol className={styles.fallbackClaims}>
          {claims.map((claim) => (
            <li key={claim.text}>
              <Text>{claim.text}</Text>
            </li>
          ))}
        </ol>
      </Stack>
    </section>
  );
}
