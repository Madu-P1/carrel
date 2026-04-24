import { signal } from "@preact/signals";
import type { ComponentChild } from "preact";

/**
 * Theme modes.
 *
 * - system: follow the OS preference via prefers-color-scheme
 * - dark / light: forced, ignore OS and time
 * - auto:  time-of-day schedule. Dark from 20:00 local to 07:00; light
 *          during daytime. No OS coupling — a user who picks "auto"
 *          wants a predictable clock-driven flip, not macOS's idea.
 *
 * The cycle through toggleTheme() is system → dark → light → auto →
 * system, so the keyboard shortcut (⌘⇧A in macOS) can reach all four.
 */
export type ThemeMode = "system" | "dark" | "light" | "auto";
type NavigateFn = (path: string) => void;

/** Hour at which auto mode flips INTO dark. Local clock, 24h. */
const AUTO_DARK_START_HOUR = 20;
/** Hour at which auto mode flips BACK to light. */
const AUTO_LIGHT_START_HOUR = 7;

const navigatorSignal = signal<NavigateFn | null>(null);
let autoThemeTimer: number | null = null;

function routeWantsRightPanel(path: string): boolean {
  return pathnameFromRoute(path).startsWith("/reader");
}

export function pathnameFromRoute(path: string): string {
  try {
    return new URL(path, "https://einstein.local").pathname;
  } catch {
    return path.split("?")[0] || "/library";
  }
}

function prefersDarkMode(): boolean {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? true;
}

/**
 * Is the local wall clock in the "night" window? True when it's at or
 * after 20:00 OR before 07:00. The window wraps across midnight, so the
 * predicate is an OR not an AND — careful not to write 20 <= h < 7 and
 * get back an always-false.
 */
function isNightHour(date: Date = new Date()): boolean {
  const h = date.getHours();
  return h >= AUTO_DARK_START_HOUR || h < AUTO_LIGHT_START_HOUR;
}

/**
 * Number of ms until the next auto-theme boundary (the next clock hour
 * that will flip the theme). If it's 14:32, the next boundary is 20:00.
 * If it's 21:15, the next boundary is 07:00 tomorrow. Always rounds up
 * to the minute so the timer fires slightly AFTER the boundary, never
 * slightly before (which would set the wrong theme for a few seconds).
 */
function msUntilNextAutoBoundary(now: Date = new Date()): number {
  const next = new Date(now);
  const h = now.getHours();
  next.setMinutes(0, 5, 0); // fire 5 s after the top of the hour
  if (h < AUTO_LIGHT_START_HOUR) {
    next.setHours(AUTO_LIGHT_START_HOUR);
  } else if (h < AUTO_DARK_START_HOUR) {
    next.setHours(AUTO_DARK_START_HOUR);
  } else {
    next.setDate(next.getDate() + 1);
    next.setHours(AUTO_LIGHT_START_HOUR);
  }
  return Math.max(1000, next.getTime() - now.getTime());
}

function applyThemeClass(theme: ThemeMode): void {
  const root = document.documentElement;
  root.classList.remove("theme-dark", "theme-light");

  let resolved: "theme-dark" | "theme-light";
  if (theme === "system") {
    resolved = prefersDarkMode() ? "theme-dark" : "theme-light";
  } else if (theme === "auto") {
    resolved = isNightHour() ? "theme-dark" : "theme-light";
  } else {
    resolved = `theme-${theme}` as "theme-dark" | "theme-light";
  }
  root.classList.add(resolved);
}

/**
 * Arm (or disarm) the auto-theme timer. Called every time the theme
 * setting changes. When the user leaves auto mode we cancel the timer
 * so we don't fight a forced setting at 20:00.
 */
function refreshAutoThemeTimer(): void {
  if (autoThemeTimer !== null) {
    window.clearTimeout(autoThemeTimer);
    autoThemeTimer = null;
  }
  if (appShell.theme.value !== "auto") return;
  const delay = msUntilNextAutoBoundary();
  autoThemeTimer = window.setTimeout(() => {
    applyThemeClass(appShell.theme.value);
    refreshAutoThemeTimer();
  }, delay);
}

/** Minimal shape the palette + sidebar consume when deciding whether to
 *  surface session-scoped shortcuts. Populated by DashboardView after
 *  each dashboard fetch; the whole app watches this signal for the
 *  source of truth on "is there a session right now?" */
export interface ActiveSessionContext {
  id: string;
  objective: string;
}

export const appShell = {
  leftOpen: signal(true),
  rightOpen: signal(false),
  theme: signal<ThemeMode>("system"),
  // Default landing route. "/" renders the Dashboard; historically this was
  // "/library" when the app had no Dashboard surface.
  currentRoute: signal("/"),
  rightPanelContent: signal<ComponentChild | null>(null),
  activeSession: signal<ActiveSessionContext | null>(null)
};

export function setActiveSession(context: ActiveSessionContext | null): void {
  appShell.activeSession.value = context;
}

export function initializeTheme(): void {
  applyThemeClass(appShell.theme.value);
  refreshAutoThemeTimer();
}

export function setCurrentRoute(path: string): void {
  appShell.currentRoute.value = path;
  appShell.rightOpen.value = routeWantsRightPanel(path);
}

export function registerNavigator(navigate: NavigateFn): () => void {
  navigatorSignal.value = navigate;
  return () => {
    if (navigatorSignal.value === navigate) {
      navigatorSignal.value = null;
    }
  };
}

export function navigateTo(path: string): void {
  const navigate = navigatorSignal.value;
  if (navigate) {
    navigate(path);
    return;
  }

  setCurrentRoute(path);
}

export function toggleLeft(): void {
  appShell.leftOpen.value = !appShell.leftOpen.value;
}

export function toggleRight(): void {
  appShell.rightOpen.value = !appShell.rightOpen.value;
}

export function toggleTheme(): void {
  const next: Record<ThemeMode, ThemeMode> = {
    system: "dark",
    dark: "light",
    light: "auto",
    auto: "system"
  };

  appShell.theme.value = next[appShell.theme.value];
  applyThemeClass(appShell.theme.value);
  refreshAutoThemeTimer();
}

export function clearRightPanelContent(): void {
  appShell.rightPanelContent.value = null;
}
