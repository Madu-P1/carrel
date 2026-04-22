import { Badge, Stack, Text } from "@/design-system";

import type { ClaimRecord } from "../types";
import styles from "../AskView.module.css";

interface FallbackAnswerProps {
  claims: ClaimRecord[];
  error?: string;
}

export function FallbackAnswer({ claims, error }: FallbackAnswerProps) {
  return (
    <section className={styles.fallbackWrap}>
      <Stack gap={3}>
        <Stack gap={1}>
          <Badge tone="warning">Fallback</Badge>
          <Text as="h2" variant="h2" weight="bold">
            AI synthesis unavailable
          </Text>
          <Text tone="secondary">
            The shell is showing raw retrieved passages instead of pretending synthesis succeeded.
          </Text>
          {error ? <Text tone="tertiary">Error: {error}</Text> : null}
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
