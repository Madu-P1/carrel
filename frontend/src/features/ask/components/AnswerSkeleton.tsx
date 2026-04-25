import { Card, Skeleton, SkeletonGroup, Stack } from "@/design-system";

import styles from "../AskView.module.css";

function AnswerSkeletonCard() {
  return (
    <Card className={styles.feedSkeletonCard} padding="md">
      <div className={styles.feedCardMeasure}>
        <Stack gap={3}>
          <Skeleton height={22} shape="text-sm" width={116} />
          <Skeleton height={24} shape="text-lg" width="54%" />
          <Skeleton height={14} shape="text" width="92%" />
          <Skeleton height={14} shape="text" width="78%" />
          <div className={styles.feedSkeletonMetaRow}>
            <div className={styles.feedSkeletonEvidence}>
              <Skeleton height={32} shape="custom" width={148} />
              <Skeleton height={12} shape="text-sm" width={220} />
            </div>
            <div className={styles.feedSkeletonActions}>
              <Skeleton height={32} shape="custom" width={68} />
              <Skeleton height={32} shape="custom" width={102} />
            </div>
          </div>
        </Stack>
      </div>
    </Card>
  );
}

export function AnswerSkeleton() {
  return (
    <SkeletonGroup label="Loading answer cards">
      <Stack data-testid="ask-answer-skeleton" gap={3}>
        {[0, 1, 2].map((index) => (
          <AnswerSkeletonCard key={index} />
        ))}
      </Stack>
    </SkeletonGroup>
  );
}
