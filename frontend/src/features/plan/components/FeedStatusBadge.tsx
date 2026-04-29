import type { CalendarFeed } from "../api/calendarApi";
import styles from "./FeedStatusBadge.module.css";

interface FeedStatusBadgeProps {
  feed: CalendarFeed;
  /** Optional: when true, render the "syncing in background" state.
   *  Driven by the global is_freshening signal, not per-feed —
   *  per-feed in-flight tracking is Phase 2. */
  isFreshening?: boolean;
}

/**
 * Compact status pill for a feed row in FeedList. Three states:
 *
 *   - syncing     accent, animated; renders while is_freshening is on
 *   - error       danger-tone; tooltip carries the masked error
 *   - synced      neutral; "Synced N min ago"
 *
 * Voice rule: error text uses concrete recovery language ("Sync didn't
 * complete — try again or check the URL"), not generic "Failed."
 */
export function FeedStatusBadge({ feed, isFreshening = false }: FeedStatusBadgeProps) {
  if (isFreshening) {
    return (
      <span className={[styles.badge, styles.syncing].join(" ")}>
        <span className={styles.dot} aria-hidden />
        Syncing
      </span>
    );
  }

  if (feed.last_error) {
    return (
      <span
        className={[styles.badge, styles.error].join(" ")}
        title={feed.last_error}
      >
        Sync error
      </span>
    );
  }

  if (feed.last_successful_sync_at) {
    return (
      <span className={[styles.badge, styles.synced].join(" ")}>
        Synced {formatRelative(feed.last_successful_sync_at)}
      </span>
    );
  }

  return (
    <span className={[styles.badge, styles.neutral].join(" ")}>Pending sync</span>
  );
}

/**
 * Coarse relative-time formatter — Plan view doesn't need second
 * precision. Buckets: "just now" / "N min ago" / "N hr ago" / "Yesterday" /
 * locale date. Mirrors the formatRelativeTime util used in Library.
 */
function formatRelative(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";

  const seconds = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (seconds < 60) return "just now";
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} hr ago`;
  if (hours < 48) return "yesterday";
  return new Date(iso).toLocaleDateString();
}
