import { useCallback, useEffect, useState } from "preact/hooks";

import { Icon } from "@/design-system";
import { dashboard, type DashboardPayload } from "@/services/api/endpoints";
import { navigateTo, setActiveSession } from "@/app/shell/useAppShell";

import { ActiveSessionCard } from "./components/ActiveSessionCard";
import { HeroAskPrompt } from "./components/HeroAskPrompt";
import { StreakRing } from "./components/StreakRing";
import { useCountUp } from "./components/useCountUp";
import { WeekSparkline } from "./components/WeekSparkline";
import styles from "./DashboardView.module.css";

/**
 * Dashboard home.
 *
 * Zone order (top to bottom):
 *   1. Greeting (eyebrow + serif)
 *   2. Hero Ask prompt — magnetic entry point into /ask
 *   3. Next Best Action — one heuristic-driven recommendation
 *   4. Active Session card — status chip (renders only when session is
 *      active or just completed)
 *   5. Quick action grid — four tiles: session, ask, review, generate
 *   6. Stat strip — streak ring, this-week w/ sparkline, sessions, sources
 *
 * Data flow:
 *   - Single fetch of /api/dashboard on mount.
 *   - Refetch on window focus (multi-tab drift).
 *   - Refetch after any session mutation from the status card.
 *   - No polling.
 */
export function DashboardView() {
  const [payload, setPayload] = useState<DashboardPayload | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await dashboard.get();
      setPayload(data);
      setError(null);
      // Publish active-session state for consumers outside this view
      // (palette contextual actions, future sidebar chip, etc). Keep
      // this in sync with what the user sees so "End current session"
      // only appears when the session card is visible.
      if (data.active_session) {
        setActiveSession({
          id: data.active_session.id,
          objective: (data.active_session.objective || "").replace(
            /^\[ui:[a-z]+\]\s*/,
            ""
          )
        });
      } else {
        setActiveSession(null);
      }
    } catch (caught) {
      setError((caught as Error).message);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  // Multi-tab coherence: when the user switches back to this tab after
  // doing something in another tab (e.g., ending a session), re-pull so
  // the dashboard reflects reality. Cheap; no polling.
  useEffect(() => {
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  if (error) {
    return (
      <div className={styles.wrap}>
        <div className={styles.errorCard}>
          <strong>Could not load your dashboard.</strong>
          <span className={styles.errorMessage}>{error}</span>
          <button type="button" className={styles.retryButton} onClick={() => void refresh()}>
            Try again
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
      <Header payload={payload} />
      <HeroAskPrompt />
      <NextBestAction payload={payload} />
      <ActiveSessionCard active={payload.active_session} onMutation={() => void refresh()} />
      <QuickActionGrid dueCards={payload.stats.due_cards} />
      <StatStrip stats={payload.stats} />
    </div>
  );
}

// ---------- Header ----------

function Header({ payload }: { payload: DashboardPayload }) {
  const greet = timeOfDayGreeting(payload.greeting.time_of_day);
  const dueCards = payload.stats.due_cards;
  const activeSession = payload.active_session;
  return (
    <header className={styles.header}>
      <span className={styles.eyebrow}>
        <span className={styles.eyebrowDot} aria-hidden />
        {payload.greeting.display_date.toUpperCase()}
      </span>
      <h1 className={styles.heading}>{greet}.</h1>
      <p className={styles.subheading}>
        Your study environment is ready. Start a session, review what you've learned,
        or ask a question grounded in your own sources.
      </p>
      {(dueCards > 0 || activeSession) && (
        <div className={styles.headerChips}>
          {dueCards > 0 && (
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
              <span className={styles.headerChipArrow} aria-hidden>→</span>
            </button>
          )}
          {activeSession && (
            <button
              type="button"
              className={styles.headerChip}
              onClick={() => navigateTo("/session")}
            >
              <Icon name="sparkle" size={14} />
              <span>Session in progress</span>
              <span className={styles.headerChipArrow} aria-hidden>→</span>
            </button>
          )}
        </div>
      )}
    </header>
  );
}

function timeOfDayGreeting(tod: DashboardPayload["greeting"]["time_of_day"]): string {
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

// ---------- Next Best Action ----------

function NextBestAction({ payload }: { payload: DashboardPayload }) {
  const { next_best_action } = payload;
  return (
    <section className={styles.nba} aria-label="Next best action">
      <span className={styles.nbaEyebrow}>{next_best_action.eyebrow.toUpperCase()}</span>
      <h2 className={styles.nbaTitle}>{next_best_action.title}</h2>
      <p className={styles.nbaReason}>{next_best_action.reason}</p>
      <div className={styles.nbaActions}>
        <button
          type="button"
          className={styles.primaryAction}
          onClick={() => navigateTo(next_best_action.primary.path)}
        >
          {next_best_action.primary.label}
          <Icon name="arrow-right" size={14} />
        </button>
        {next_best_action.secondary && (
          <button
            type="button"
            className={styles.secondaryAction}
            onClick={() =>
              navigateTo(next_best_action.secondary!.path)
            }
          >
            {next_best_action.secondary.label}
          </button>
        )}
      </div>
    </section>
  );
}

// ---------- Quick Action Grid ----------

interface QuickTile {
  icon: "study" | "ask" | "doc" | "sparkle";
  title: string;
  meta: string;
  path: string;
}

function QuickActionGrid({ dueCards }: { dueCards: number }) {
  const tiles: QuickTile[] = [
    {
      icon: "study",
      title: "Start session",
      meta: "Focused deep work",
      path: "/session"
    },
    {
      icon: "ask",
      title: "Ask tutor",
      meta: "Grounded in sources",
      path: "/ask"
    },
    {
      icon: "doc",
      title: "Review cards",
      meta: dueCards > 0
        ? `${dueCards} card${dueCards === 1 ? "" : "s"} due`
        : "Nothing due",
      path: "/study"
    },
    {
      icon: "sparkle",
      title: "Generate artifact",
      meta: "Summary, flashcards, quiz",
      path: "/library"
    }
  ];
  return (
    <section className={styles.quickGrid} aria-label="Quick actions">
      {tiles.map((tile) => (
        <button
          key={tile.title}
          type="button"
          className={styles.quickTile}
          onClick={() => navigateTo(tile.path)}
        >
          <span className={styles.quickIcon} aria-hidden>
            <Icon name={tile.icon} size={18} />
          </span>
          <span className={styles.quickTitle}>{tile.title}</span>
          <span className={styles.quickMeta}>{tile.meta}</span>
        </button>
      ))}
    </section>
  );
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

/**
 * The headline numerical value on a stat cell — count-ups from 0 on
 * mount. Uses tabular nums so the serif numerals don't shift width as
 * they tick upward.
 */
function AnimatedStatValue({
  value,
  decimals = 0
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
  suffix
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
