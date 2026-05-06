import type { ComponentChildren } from "preact";

import { Button, Card, Stack } from "@/design-system";
import { renderMarkdown } from "@/lib/markdown";

import styles from "../AskView.module.css";

export interface AnswerFeedAction {
  label: string;
  onClick: () => void;
  ariaLabel?: string;
  disabled?: boolean;
}

interface AnswerFeedCardProps {
  title: string;
  body?: string;
  evidence?: ComponentChildren;
  actions?: AnswerFeedAction[];
  delayMs?: number;
  eyebrow?: ComponentChildren;
  selected?: boolean;
  selectAffordance?: ComponentChildren;
}

export function AnswerFeedCard({
  title,
  body,
  evidence,
  actions = [],
  delayMs = 0,
  eyebrow,
  selected = false,
  selectAffordance
}: AnswerFeedCardProps) {
  return (
    <article
      className={[styles.feedCardShell, "anim-fadeUp"].join(" ")}
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <Card
        className={[styles.feedCard, selected ? styles.feedCardSelected : ""].filter(Boolean).join(" ")}
        padding="md"
      >
        <div className={styles.feedCardFrame}>
          {selectAffordance ? <div className={styles.feedCardSelect}>{selectAffordance}</div> : null}
          <div className={styles.feedCardMeasure}>
            <Stack gap={3}>
              {eyebrow ? <div className={styles.feedCardEyebrow}>{eyebrow}</div> : null}
              <div className={[styles.prose, styles.feedCardTitle].join(" ")}>
                {renderMarkdown(title)}
              </div>
              {body ? (
                <div className={[styles.prose, styles.feedCardBody].join(" ")}>
                  {renderMarkdown(body)}
                </div>
              ) : null}
              {evidence || actions.length > 0 ? (
                <div className={styles.feedCardMetaRow}>
                  <div className={styles.feedCardEvidence}>{evidence}</div>
                  {actions.length > 0 ? (
                    <div className={styles.feedCardActions}>
                      {actions.map((action) => (
                        <Button
                          aria-label={action.ariaLabel ?? action.label}
                          disabled={action.disabled}
                          key={action.label}
                          onClick={() => {
                            action.onClick();
                          }}
                          size="sm"
                          type="button"
                          variant="ghost"
                        >
                          {action.label}
                        </Button>
                      ))}
                    </div>
                  ) : null}
                </div>
              ) : null}
            </Stack>
          </div>
        </div>
      </Card>
    </article>
  );
}
