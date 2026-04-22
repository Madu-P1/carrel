import { Card, Stack } from "@/design-system";

import styles from "../AskView.module.css";

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={[styles.skeletonBlock, className ?? ""].filter(Boolean).join(" ")} />;
}

export function AnswerSkeleton() {
  return (
    <Stack data-testid="ask-answer-skeleton" gap={4}>
      <Card className={styles.summaryCard} padding="lg">
        <Stack gap={3}>
          <SkeletonBlock className={styles.skeletonBadge} />
          <SkeletonBlock className={styles.skeletonTitle} />
          <SkeletonBlock className={styles.skeletonBody} />
        </Stack>
      </Card>
      <div className={styles.claimList}>
        {[0, 1].map((index) => (
          <article className={styles.claimCard} key={index}>
            <Stack gap={3}>
              <SkeletonBlock className={styles.skeletonClaim} />
              <div className={styles.citationRow}>
                <SkeletonBlock className={styles.skeletonChip} />
              </div>
            </Stack>
          </article>
        ))}
      </div>
    </Stack>
  );
}
