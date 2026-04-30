import { useCallback, useEffect, useState } from "preact/hooks";

import { Icon } from "@/design-system";
import { dashboard, type DashboardPayload } from "@/services/api/endpoints";
import { friendlyError } from "@/services/api/errorMessages";
import { navigateTo, setActiveSession } from "@/app/shell/useAppShell";

import { ActiveSessionCard } from "./components/ActiveSessionCard";
import { ContinueModule } from "./components/ContinueModule";
import { HeroAskPrompt } from "./components/HeroAskPrompt";
import { NextBestAction } from "./components/NextBestAction";
import { QuickActionGrid } from "./components/QuickActionGrid";
import { StreakRing } from "./components/StreakRing";
import { useCountUp } from "./components/useCountUp";
import { WeakConceptsRail } from "./components/WeakConceptsRail";
import { WeekSparkline } from "./components/WeekSparkline";
import styles from "./DashboardView.module.css";

/**
 * Dashboard home — the cockpit's landing page.
 *
 * Premium UI ship 6 reorganised the page hierarchy. The critique called
 * the prior layout "a stack of cards with weak orchestration." Two
 * fixes in this rebuild:
 *   1. Urgent info (cards-due / session-in-progress chips) moved
 *      ABOVE the greeting — eye-level info first, decorative title
 *      after. Per the critique, the chip row is the user's
 *      "do something now" signal and shouldn't sit underneath
 *      decorative text.
 *   2. Two anchor objects on the page now: the Hero composer (the
 *      strongest CTA, "ask anything") and the Next-Best-Action card
 *      (one decisive recommendation). Quick-action tiles and the
 *      stats strip are subordinate, not competing.
 *
 * Order from top to bottom:
 *   1. Status chips row (cards-due / session-in-progress) — urgent first
 *   2. Greeting block (eyebrow date + serif greeting + subhead)
 *   3. HeroAskPrompt — the dominant composer, max 760px clamp
 *   4. NextBestAction — one card, accent-tint (no more yellow)
 *   5. ContinueModule — resume the active session if any
 *   6. ActiveSessionCard — full status card (renders only if active)
 *   7. QuickActionGrid — 4 compact tiles
 *   8. StatStrip — streak / week / sessions / sources
 *
 * Data flow:
 *   - Single fetch of /api/dashboard on mount.
 *   - Refetch on window focus (multi-tab drift).
 *   - Refetch after any session mutation from the status card.
 *   - No polling.
 */
export function DashboardView() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  // Hold the raw Error so the error renderer can branch on its kind
  // (BackendOfflineError vs ApiError vs anything else). Storing just
  // .message would discard the type info we need to give the user a
  // useful recovery hint.
  const [error, setError] = useState<unknown>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await dashboard.get();
      setPayload(data);
      setError(null);
      // Publish active-session state for consumers outside this view
      // (palette contextual actions, sidebar chip, etc).
      if (data.active_session) {
        setActiveSession({
          id: data.active_session.id,
          objective: (data.active_session.objective || "").replace(
            /^\[ui:[a-z]+\]\s*/,
            ""
          ),
        });
      } else {
        setActiveSession(null);
      }
    } catch (caught) {
      setError(caught);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Multi-tab coherence: when the user switches back to this tab after
  // doing something in another tab (e.g., ending a session), re-pull so
  // the dashboard reflects reality.
  useEffect(() => {
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  if (error) {
    const friendly = friendlyError(error, { surface: "Dashboard" });
    return (
      <div className={styles.wrap}>
        <div className={styles.errorCard}>
          <strong>{friendly.title}</strong>
          <span className={styles.errorMessage}>{friendly.detail}</span>
          {friendly.recovery ? (
            <span className={styles.errorMessage}>{friendly.recovery}</span>
          ) : null}
          <button
            type="button"
            className={styles.retryButton}
            onClick={() => void refresh()}
          >
            Reload the dashboard
          </button>
        </div>
      </div>
    );
  }

  if (!payload) {
    return (
      <div className={styles.wrap}>
        <div className={styles.skeletonHeader} />
        <div className={styles.skeletonAction} />
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <StatusChipsRow payload={payload} />
      <Header payload={payload} />
      <HeroAskPrompt />
      <NextBestAction next={payload.next_best_action} />
      <ContinueModule active={payload.active_session} />
      <ActiveSessionCard
        active={payload.active_session}
        onMutation={() => void refresh()}
      />
      <WeakConceptsRail concepts={payload.weak_concepts ?? []} />
      <QuickActionGrid dueCards={payload.stats.due_cards} />
      <StatStrip stats={payload.stats} />
    </div>
  );
}

// ---------- Status chips row (above the greeting) ----------

/**
 * Urgent info first. Cards-due and session-in-progress chips sit above
 * the decorative greeting so the user sees what to act on before they
 * read the headline. If neither chip applies, the row renders nothing
 * (no empty placeholder — would feel like dead space).
 */
function StatusChipsRow({ payload }: { payload: DashboardPayload }) {
  const dueCards = payload.stats.due_cards;
  const activeSession = payload.active_session;
  if (dueCards <= 0 && !activeSession) return null;

  return (
    <div className={styles.statusChips} aria-label="At-a-glance status">
      {dueCards > 0 ? (
        <button
          type="button"
          className={[styles.headerChip, styles.headerChipDue].join(" ")}
          onClick={() => navigateTo("/study")}
        >
          <Icon name="study" size={14} />
          <span>
            <span className={styles.headerChipCount}>{dueCards}</span>{" "}
            card{dueCards === 1 ? "" : "s"} due now
          </span>
          <span className={styles.headerChipArrow} aria-hidden>
            →
          </span>
        </button>
      ) : null}
      {activeSession ? (
        <button
          type="button"
          className={styles.headerChip}
          onClick={() => navigateTo("/session")}
        >
          <Icon name="sparkle" size={14} />
          <span>Session in progress</span>
          <span className={styles.headerChipArrow} aria-hidden>
            →
          </span>
        </button>
      ) : null}
    </div>
  );
}

// ---------- Header ----------

function Header({ payload }: { payload: DashboardPayload }) {
  const greet = timeOfDayGreeting(payload.greeting.time_of_day);
  return (
    <header className={styles.header}>
      <span className={styles.eyebrow}>
        <span className={styles.eyebrowDot} aria-hidden />
        {payload.greeting.display_date.toUpperCase()}
      </span>
      <h1 className={styles.heading}>{greet}.</h1>
      <p className={styles.subheading}>
        Your study environment is ready. Start a session, review what
        you've learned, or ask a question grounded in your own sources.
      </p>
    </header>
  );
}

function timeOfDayGreeting(
  tod: DashboardPayload["greeting"]["time_of_day"]
): string {
  switch (tod) {
    case "morning":
      return "Good morning";
    case "afternoon":
      return "Good afternoon";
    case "evening":
      return "Good evening";
    case "night":
      return "Working late";
    default:
      return "Welcome back";
  }
}

// ---------- Stat Strip ----------

function StatStrip({ stats }: { stats: DashboardPayload["stats"] }) {
  return (
    <section className={styles.stats} aria-label="Weekly stats">
      <div className={styles.streakCell}>
        <span className={styles.statLabel}>STREAK</span>
        <StreakRing
          streakDays={stats.streak_days}
          targetDays={stats.streak_target_days}
        />
      </div>
      <div className={styles.statCell}>
        <span className={styles.statLabel}>THIS WEEK</span>
        <div className={styles.statValueRow}>
          <AnimatedStatValue value={stats.week_minutes / 60} decimals={1} />
          <span className={styles.statSuffix}>h</span>
        </div>
        <WeekSparkline minutesByDay={stats.week_minutes_by_day} />
      </div>
      <StatBlock
        label="Sessions today"
        value={stats.sessions_today}
        suffix={stats.sessions_today === 1 ? "session" : "sessions"}
      />
      <StatBlock
        label="Sources"
        value={stats.source_count}
        suffix={stats.source_count === 1 ? "document" : "documents"}
      />
    </section>
  );
}

function AnimatedStatValue({
  value,
  decimals = 0,
}: {
  value: number;
  decimals?: number;
}) {
  const rendered = useCountUp(value, 700, decimals);
  return <span className={styles.statValue}>{rendered}</span>;
}

function StatBlock({
  label,
  value,
  suffix,
}: {
  label: string;
  value: number;
  suffix: string;
}) {
  return (
    <div className={styles.statCell}>
      <span className={styles.statLabel}>{label.toUpperCase()}</span>
      <div className={styles.statValueRow}>
        <AnimatedStatValue value={value} />
        <span className={styles.statSuffix}>{suffix}</span>
      </div>
    </div>
  );
}
