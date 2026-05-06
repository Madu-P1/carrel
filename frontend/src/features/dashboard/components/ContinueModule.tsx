import { navigateTo } from "@/app/shell/useAppShell";
import { Icon } from "@/design-system";
import type { ActiveSessionSummary } from "@/services/api/endpoints";

import styles from "./ContinueModule.module.css";

interface ContinueModuleProps {
  active: ActiveSessionSummary | null;
}

/**
 * ContinueModule — "Continue where you left off."
 *
 * Premium UI ship 6 added this band. It renders only when there's a
 * recent session worth resuming — currently that's the active_session
 * field on the dashboard payload. (Future: a "last opened doc" pointer
 * so a user who closed the reader can pick the same source back up.)
 *
 * Compact horizontal layout — single row, eyebrow + title + resume
 * button on the right. Subordinate visual weight (no shadow, hairline
 * border) so the page hierarchy stays Hero composer > Recommendation >
 * Continue > Quick actions > Stats.
 *
 * The objective string round-trips through the [ui:mode] prefix used by
 * SessionView, so the component strips that prefix before display —
 * matches what the sidebar and palette show, never the raw stored text.
 */
export function ContinueModule({ active }: ContinueModuleProps) {
  if (!active) return null;
  const cleanObjective = (active.objective || "").replace(/^\[ui:[a-z]+\]\s*/, "");
  const display = cleanObjective.trim() || "Active session";

  return (
    <aside
      className={styles.band}
      aria-label="Continue where you left off"
    >
      <div className={styles.body}>
        <span className={styles.eyebrow}>Continue where you left off</span>
        <span className={styles.title}>{display}</span>
      </div>
      <button
        type="button"
        className={styles.resume}
        onClick={() => navigateTo("/session")}
      >
        Resume
        <Icon name="arrow-right" size={14} />
      </button>
    </aside>
  );
}
