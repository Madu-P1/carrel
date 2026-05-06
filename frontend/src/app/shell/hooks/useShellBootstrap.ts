import { useEffect, useRef } from "preact/hooks";

import { events } from "@/services/metrics/events";

import {
  appShell,
  initializeTheme,
  registerNavigator,
  setCurrentRoute
} from "../useAppShell";

const FIRST_LAUNCH_EVENT_KEY = "carrel.metrics.first-launch-recorded";

// Module-level guard for the localStorage-throws fallback path. Without
// this, every shell remount in private mode / file:// re-throws the
// getItem call and the catch branch re-emits `app.first_launch` —
// turning "first launch" into "every mount." We can't rely on the
// localStorage marker here (the throw is what put us in the catch
// branch), so this in-memory flag is the only correct guard.
let firstLaunchEmittedThisProcess = false;

interface ShellBootstrapOptions {
  navigate: (path: string) => void;
  path: string;
}

/**
 * One-time + per-route shell wiring. Runs on mount:
 *   - initializeTheme(): apply persisted/system theme to <html>.
 *   - emit `app.first_launch` exactly once via a localStorage marker.
 *
 * On every `path` change: pushes the route into the appShell signal so
 * the bundled-mode entry stays in sync. (Browser mode goes through
 * preact-iso's LocationProvider; the duplicate-write is cheap and keeps
 * BundledAppShell working without a second code path.)
 *
 * On every `navigate` change: re-registers the navigator function so
 * `navigateTo()` calls from anywhere in the app reach the right router.
 */
export function useShellBootstrap({ navigate, path }: ShellBootstrapOptions): void {
  useEffect(() => {
    initializeTheme();
    try {
      if (window.localStorage.getItem(FIRST_LAUNCH_EVENT_KEY) !== "1") {
        window.localStorage.setItem(FIRST_LAUNCH_EVENT_KEY, "1");
        void events.track("app.first_launch", { theme: appShell.theme.value }, "app");
      }
    } catch {
      // localStorage may throw in private mode / file:// quirks. Emit
      // the event once per process so we don't lose first-launch signal,
      // but guard with a module-level flag so a remount doesn't re-fire.
      if (!firstLaunchEmittedThisProcess) {
        firstLaunchEmittedThisProcess = true;
        void events.track("app.first_launch", { theme: appShell.theme.value }, "app");
      }
    }
  }, []);

  useEffect(() => {
    setCurrentRoute(path);
  }, [path]);

  // preact-iso's `useLocation().route` returns a fresh function reference
  // on every render, so a naïve `useEffect(..., [navigate])` would tear
  // down + re-register on every keystroke or signal flip — between the
  // teardown and the new effect, navigatorSignal is null, and any
  // navigateTo() called in that microtask window would silently fall
  // through to setCurrentRoute (browser mode = no actual navigation).
  //
  // Stabilize via a ref: register a stable wrapper once on mount, keep
  // the latest navigate callback in the ref, and let the wrapper read
  // the ref at call time.
  const navigateRef = useRef(navigate);
  navigateRef.current = navigate;
  useEffect(() => registerNavigator((nextPath) => navigateRef.current(nextPath)), []);
}
