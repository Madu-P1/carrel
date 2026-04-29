import type { CalendarFeed } from "../api/calendarApi";
import { Button, Icon } from "@/design-system";
import { FeedStatusBadge } from "./FeedStatusBadge";
import styles from "./FeedList.module.css";

interface FeedListProps {
  feeds: CalendarFeed[];
  isFreshening: boolean;
  onSync: (feedId: string) => void;
  onDelete: (feed: CalendarFeed) => void;
  onAddFeed: () => void;
}

/**
 * Persistent feed list — renders each feed with its status badge,
 * a per-feed "Sync now" button, and a delete affordance.
 *
 * The masked URL is shown beneath the label as a tertiary line so
 * the user can tell "Personal Calendar" (Apple) apart from "Personal
 * Calendar" (Google) without revealing the auth token.
 */
export function FeedList({
  feeds,
  isFreshening,
  onSync,
  onDelete,
  onAddFeed,
}: FeedListProps) {
  return (
    <section className={styles.list} aria-label="Calendar feeds">
      <header className={styles.header}>
        <span className={styles.eyebrow}>Calendar feeds</span>
        <Button
          leadingIcon={<Icon name="plus" size={14} />}
          onClick={onAddFeed}
          size="sm"
          variant="secondary"
        >
          Add feed
        </Button>
      </header>
      {feeds.length === 0 ? (
        <p className={styles.emptyHint}>
          No calendars connected. Add one to see your week here.
        </p>
      ) : (
        <ul className={styles.rows}>
          {feeds.map((feed) => (
            <li className={styles.row} key={feed.id}>
              <span
                className={styles.colorDot}
                style={{ background: feed.color ?? "var(--color-accent)" }}
                aria-hidden
              />
              <div className={styles.body}>
                <span className={styles.label}>{feed.label}</span>
                <span className={styles.meta} title={feed.url}>
                  {feed.url}
                </span>
              </div>
              <FeedStatusBadge feed={feed} isFreshening={isFreshening} />
              <div className={styles.rowActions}>
                <button
                  type="button"
                  className={styles.iconBtn}
                  aria-label={`Sync ${feed.label} now`}
                  onClick={() => onSync(feed.id)}
                >
                  <Icon name="arrow-right" size={14} />
                </button>
                <button
                  type="button"
                  className={styles.iconBtn}
                  aria-label={`Delete ${feed.label}`}
                  onClick={() => onDelete(feed)}
                >
                  <Icon name="trash" size={14} />
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
