import { signal } from "@preact/signals";
import type { ComponentChild } from "preact";

export type ThemeMode = "system" | "dark" | "light";
type NavigateFn = (path: string) => void;

const navigatorSignal = signal<NavigateFn | null>(null);

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

function applyThemeClass(theme: ThemeMode): void {
  const root = document.documentElement;
  root.classList.remove("theme-dark", "theme-light");

  const resolved = theme === "system" ? (prefersDarkMode() ? "theme-dark" : "theme-light") : `theme-${theme}`;
  root.classList.add(resolved);
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
    light: "system"
  };

  appShell.theme.value = next[appShell.theme.value];
  applyThemeClass(appShell.theme.value);
}

export function clearRightPanelContent(): void {
  appShell.rightPanelContent.value = null;
}
