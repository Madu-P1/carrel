import { Stack, Text } from "@/design-system";

import type { CitationRecord, ClaimRecord } from "../types";
import { CitationChip } from "./CitationChip";
import styles from "../AskView.module.css";

interface ClaimListProps {
  claims: ClaimRecord[];
  onCitationClick?: (citation: CitationRecord) => void;
}

export function ClaimList({ claims, onCitationClick }: ClaimListProps) {
  // Citations are indexed globally across the answer, not per-claim, so the
  // `[1]` `[2]` `[3]` in chip labels matches what the user scans visually.
  let runningIndex = 0;
  return (
    <div className={styles.claimList}>
      {claims.map((claim, index) => {
        const claimDelay = 80 + index * 60;
        const citationDelay = claimDelay + 120;

        return (
          <article
            className={[styles.claimCard, "anim-fadeUp"].join(" ")}
            key={claim.text}
            style={{ animationDelay: `${claimDelay}ms` }}
          >
          <Stack gap={3}>
            <Text weight="medium">{claim.text}</Text>
            <div className={styles.citationRow}>
              {claim.citations.map((citation) => {
                runningIndex += 1;
                return (
                  <CitationChip
                    citation={citation}
                    index={runningIndex}
                    delayMs={citationDelay}
                    key={`${claim.text}-${citation.chunk_id}`}
                    onClick={onCitationClick}
                  />
                );
              })}
            </div>
          </Stack>
          </article>
        );
      })}
    </div>
  );
}
