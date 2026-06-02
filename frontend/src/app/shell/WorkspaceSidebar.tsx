import { Icon } from "@/design-system";

import { SubjectRail } from "@/features/notes/components/SubjectRail";

import { BrandMark } from "./BrandMark";
import { buildSidebarSections, type SidebarNavItem } from "./sidebarSections";
import { appShell, toggleLeft, toggleNotesRailMode } from "./useAppShell";
import { useSidebarSignals } from "./useSidebarSignals";
import styles from "./WorkspaceSidebar.module.css";

// Re-exported so existing importers (AppShell) keep importing the type from
// here; the definition now lives in the pure ./sidebarSections module.
export type { SidebarNavItem } from "./sidebarSections";

interface WorkspaceSidebarProps {
  /** Pathname to compute the active item against. */
  pathname: string;
  items: SidebarNavItem[];
  onNavigate: (path: string) => void;
  /** When true, the sidebar renders in "icon rail" mode — only the
   *  BrandMark is visible and clicking it expands the sidebar again.
   *  The nav, today panel, and footer stay in the DOM (hidden with
   *  CSS) so expanding doesn't re-mount them. */
  collapsed?: boolean;
}

/**
 * Dense, informative left rail.
 *
 * Zones (top to bottom):
 *   1. Brand — app identity, always visible.
 *   2. Navigate — the four workspace destinations with live signals:
 *      Library shows total source count; Study shows SRS due count.
 *      Active item gets a 2px accent rail, hover lifts, idle stays quiet.
 *   3. Today — at-a-glance status for the current day. "N cards due · M new
 *      sources today" with a one-click jump into the review flow. Hides
 *      itself when there's nothing to say instead of showing filler.
 *   4. Provider footer — trust signal. Shows whether the app is running on
 *      cloud (Claude) or local (Ollama), plus the specific model id.
 *      Dot color communicates status: accent=healthy, warn=unknown/error.
 *
 * The component is a pure view over `useSidebarSignals` — all data fetches
 * live in the hook, this renders what it's told.
 */
export function WorkspaceSidebar({
  pathname,
  items,
  onNavigate,
  collapsed = false
}: WorkspaceSidebarProps) {
  const signals = useSidebarSignals();
  const dueCount = signals.dueCount ?? 0;

  // When the user is on /notes AND the rail-replacement signal is on
  // (default), the rail's middle nav section swaps to the Notes
  // Workspace+Subjects content. The brand mark, TodayPanel, and
  // ProviderFooter persist — only the middle section changes. Clicking
  // the brand mark toggles between the two modes.
  const isNotesRailActive =
    pathname.startsWith("/notes") && appShell.notesRailReplacement.value;

  const sections = buildSidebarSections(items);

  const isItemActive = (item: SidebarNavItem) => {
    // "/" only matches the Dashboard exactly — otherwise Library would
    // also activate on the dashboard route because every path starts with "/".
    if (item.path === "/") return pathname === "/";
    return pathname.startsWith(item.path);
  };

  return (
    <div
      className={[
        styles.sidebar,
        collapsed ? styles.sidebarCollapsed : "",
        isNotesRailActive ? styles.sidebarNotesMode : ""
      ]
        .filter(Boolean)
        .join(" ")}
      data-notes-rail={isNotesRailActive ? "true" : "false"}
    >
      {/*
       * Sidebar brand: icon-only. Clicking it collapses the sidebar —
       * matches the Linear/Raycast pattern where the brand mark IS the
       * toggle. The "Carrel / Study tutor" text that used to sit here
       * duplicated information already in the top bar.
       *
       * When collapsed (icon-rail mode), the brand tile is the ONLY
       * visible thing in the rail, so a second click brings the
       * sidebar back. The aria-label flips between "Collapse sidebar"
       * and "Expand sidebar" so screen-reader users hear the current
       * affordance, not a generic "Toggle".
       */}
      <header className={styles.brand}>
        <BrandMark
          ariaLabel={
            pathname.startsWith("/notes")
              ? isNotesRailActive
                ? "Show workspace navigation"
                : "Return to Notes rail"
              : collapsed
                ? "Expand sidebar"
                : "Collapse sidebar"
          }
          onClick={() => {
            // On /notes, the brand mark toggles between two rail
            // CONTENTS within the same physical rail slot:
            //   - Notes Workspace+Subjects (default when entering /notes)
            //   - Global workspace navigation
            // The logo itself never moves — only what's underneath
            // swaps with a fade. Off /notes the click reverts to the
            // existing collapse-toggle behavior.
            if (pathname.startsWith("/notes")) {
              toggleNotesRailMode();
              return;
            }
            toggleLeft();
          }}
          title={
            pathname.startsWith("/notes")
              ? isNotesRailActive
                ? "Show workspace navigation"
                : "Return to Notes rail"
              : collapsed
                ? "Expand sidebar (⌘B)"
                : "Collapse sidebar (⌘B)"
          }
        />
      </header>

      {isNotesRailActive ? (
        <div className={styles.notesRailSlot} aria-label="Notes navigation">
          <SubjectRail />
        </div>
      ) : (
        <nav className={styles.nav} aria-label="Workspace navigation">
          {sections.map((section) => (
            <div className={styles.navSection} key={section.label}>
              <span className={styles.sectionLabel}>{section.label}</span>
              <ul className={styles.navList}>
                {section.items.map((item) => {
                  const active = isItemActive(item);
                  const badge =
                    item.key === "study" && dueCount > 0 ? dueCount : null;
                  return (
                    <li key={item.path}>
                      <button
                        type="button"
                        className={[
                          styles.navItem,
                          active ? styles.navItemActive : ""
                        ]
                          .filter(Boolean)
                          .join(" ")}
                        onClick={() => onNavigate(item.path)}
                        aria-current={active ? "page" : undefined}
                        aria-label={`Open ${item.label}${
                          item.key === "study" && badge !== null
                            ? `, ${badge} due`
                            : ""
                        }`}
                      >
                        <span className={styles.navIcon} aria-hidden>
                          <Icon name={item.icon} size={16} />
                        </span>
                        <span className={styles.navLabel}>{item.label}</span>
                        {badge !== null && (
                          <span
                            className={styles.navBadge}
                            aria-label={`${badge} cards due`}
                          >
                            {badge}
                          </span>
                        )}
                        <span className={styles.navHint} aria-hidden>
                          {item.commandHint}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))}
        </nav>
      )}

      <TodayPanel
        dueCount={signals.dueCount}
        docCount={signals.docCount}
        onStartReview={() => onNavigate("/study")}
      />

      <ProviderFooter
        provider={signals.provider}
        backend={signals.backend}
      />
    </div>
  );
}

interface TodayPanelProps {
  dueCount: number | null;
  docCount: number | null;
  onStartReview: () => void;
}

function TodayPanel({ dueCount, docCount, onStartReview }: TodayPanelProps) {
  const hasReview = typeof dueCount === "number" && dueCount > 0;
  const hasLibrary = typeof docCount === "number" && docCount > 0;

  if (!hasReview && !hasLibrary) {
    // Nothing concrete to report yet — we don't render a filler panel.
    // The nav above is enough information density.
    return null;
  }

  return (
    <section className={styles.today} aria-label="Today">
      <span className={styles.sectionLabel}>Today</span>
      <div className={styles.todayStats}>
        {hasReview ? (
          <span className={styles.todayStat}>
            <strong>{dueCount}</strong> card{dueCount === 1 ? "" : "s"} due
          </span>
        ) : hasLibrary ? (
          <span className={styles.todayStat}>No cards due.</span>
        ) : null}
        {hasLibrary ? (
          <span className={styles.todayStatMuted}>
            {docCount} source{docCount === 1 ? "" : "s"} in library
          </span>
        ) : null}
      </div>
      {hasReview && (
        <button
          type="button"
          className={styles.todayAction}
          onClick={onStartReview}
        >
          <span>Start review</span>
          <Icon name="arrow-right" size={14} />
        </button>
      )}
    </section>
  );
}

function ProviderFooter({
  provider,
  backend
}: {
  provider: ReturnType<typeof useSidebarSignals>["provider"];
  backend: ReturnType<typeof useSidebarSignals>["backend"];
}) {
  // Backend liveness takes priority over the provider chip. If the
  // FastAPI process is unreachable, EVERY API call is failing — the
  // user needs to see "backend offline" first, before the AI chip's
  // "AI disabled" reading (which is a downstream symptom: the
  // provider check fails because it can't reach the backend).
  if (backend === "down") {
    return (
      <footer className={styles.footer} aria-label="Backend status">
        <span
          className={[styles.footerDot, styles.footerDotErr].join(" ")}
          aria-hidden
        />
        <span
          className={styles.footerText}
          title="The FastAPI backend at 127.0.0.1:8000 isn't responding. The desktop app's BackendSupervisor probes every 60s and respawns it on failure. This should clear within a minute. If it doesn't, run `bash script/build_and_run.sh`."
        >
          Backend offline
        </span>
      </footer>
    );
  }

  if (!provider) {
    return (
      <footer className={styles.footer} aria-label="Provider status">
        <span className={[styles.footerDot, styles.footerDotLoading].join(" ")} aria-hidden />
        <span className={styles.footerText}>Checking provider…</span>
      </footer>
    );
  }

  const label = providerLabel(provider);
  const isHealthy = provider.ai_enabled && provider.kind !== "unknown";
  const dotClass = [
    styles.footerDot,
    isHealthy ? styles.footerDotOk : styles.footerDotWarn
  ].join(" ");

  return (
    <footer className={styles.footer} aria-label="Provider status">
      <span className={dotClass} aria-hidden />
      <span className={styles.footerText} title={providerTitle(provider)}>
        {label}
      </span>
    </footer>
  );
}

function providerLabel(provider: {
  kind: string;
  model_balanced: string;
  ai_enabled: boolean;
}): string {
  if (!provider.ai_enabled) {
    return "AI disabled";
  }
  const model = provider.model_balanced || provider.kind || "unknown";
  const suffix =
    provider.kind === "ollama"
      ? "local"
      : provider.kind === "claude"
      ? "cloud"
      : provider.kind;
  return `${model} · ${suffix}`;
}

function providerTitle(provider: {
  kind: string;
  preference: string;
  model_balanced: string;
}): string {
  return `Provider: ${provider.kind} · preference: ${provider.preference}${
    provider.model_balanced ? ` · model: ${provider.model_balanced}` : ""
  }`;
}
