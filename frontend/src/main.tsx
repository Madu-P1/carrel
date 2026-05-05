import { effect } from "@preact/signals";
import { render } from "preact";

import { App } from "./app/App";
import { markAppBootedAfterInteractive } from "./app/shell/boot";
import { appShell, initializeTheme } from "./app/shell/useAppShell";
import { documentsQuery } from "./features/library/hooks/useDocumentsQuery";
import { startJobsFeed } from "./features/shell/jobsStore";
import { companion } from "./services/companion/bus";
import { installInsertionAlarmWatcher } from "./services/companion/insertionAlarm";
import { reportInteractive } from "./services/native/telemetry";
import "./main.css";

// Start the jobs SSE feed at boot, not just when the Jobs tray opens.
// The feed observes every ingestion job — including ones the user
// triggered via the floating cube, the CLI, or any future external
// source — and refetches the Library on each event. Without this,
// external uploads don't surface in the in-app Library until the user
// manually opens the Jobs tray.
startJobsFeed();

// Companion idle/wake watcher. Pushes the cube into 'sleeping' after
// 15 minutes of no input (matches the spec §5 idle threshold) and
// wakes on any user activity. Per-feature state pushes (session,
// tutor, SRS) are wired at their call sites via the same bus.
companion.installIdleWatcher();

// Insertion alarm: when the next planned study session's start time
// arrives (per `/api/plan/insertions`), the floating cube spins
// chaotically. Tapping the panel dismisses the alarm and brings the
// main window forward so the user can hit Start.
installInsertionAlarmWatcher();

// Session start/end is the single most legible event for the user.
// Subscribe to the global activeSession signal so the cube reflects
// session state regardless of which path flipped it (manual end,
// completion, palette command, browser-back from SessionView).
let lastSessionActive: boolean | undefined;
effect(() => {
  const isActive = appShell.activeSession.value !== null;
  if (lastSessionActive === undefined) {
    // First read is the initial value — never fire on boot.
    lastSessionActive = isActive;
    return;
  }
  if (isActive === lastSessionActive) return;
  if (isActive) companion.sessionStart();
  else companion.sessionEnd();
  lastSessionActive = isActive;
});

// Floating-companion → in-app refresh bridge (belt + suspenders).
// The Swift bridge calls this after each successful drop in case the
// SSE stream is offline (e.g. backend restart racing the upload).
(window as unknown as { __carrelRefreshLibrary?: () => void }).__carrelRefreshLibrary = () => {
  void documentsQuery.refetch();
};

// Refetch Library when the user comes back to Carrel. Catches the
// case where SSE silently dropped (sleep/wake, backend hiccup) and
// the user dropped files on the cube while another app was frontmost.
window.addEventListener("focus", () => { void documentsQuery.refetch(); });
document.addEventListener("visibilitychange", () => {
  if (!document.hidden) void documentsQuery.refetch();
});

const bootWindow = window as typeof window & {
  nativeTelemetry?: { emit: (event: string, payload?: Record<string, unknown>) => void };
  __einsteinMainStarted?: boolean;
};

bootWindow.__einsteinMainStarted = true;
bootWindow.nativeTelemetry?.emit("main-script-start", {
  href: window.location.href
});

// TEMP DEBUG: surface any uncaught JS error or rejected promise as a
// fixed red banner pinned to the top of the page. Lets us debug the
// blank-Reader issue without needing WKWebView devtools open.
function showGlobalDebugBanner(prefix: string, info: string) {
  let banner = document.getElementById("__einstein_debug_banner");
  if (!banner) {
    banner = document.createElement("div");
    banner.id = "__einstein_debug_banner";
    banner.style.cssText =
      "position:fixed;top:0;left:0;right:0;z-index:99999;" +
      "background:#7a0010;color:#fff;font-family:monospace;font-size:12px;" +
      "padding:10px 14px;white-space:pre-wrap;max-height:40vh;overflow:auto;" +
      "border-bottom:2px solid #ff3a3a;";
    document.body?.appendChild(banner);
  }
  banner.textContent =
    (banner.textContent || "") + "\n[" + prefix + "] " + info;
}

/**
 * Known-benign error messages we filter out of the debug banner. These
 * fire constantly under WKWebView and aren't real bugs:
 *
 * - "ResizeObserver loop completed with undelivered notifications" (and
 *   the older "ResizeObserver loop limit exceeded" wording): the
 *   browser saw a potential layout-feedback loop and dropped one
 *   notification rather than spinning. Safe to suppress; every modern
 *   app emits this. Filtering at the global level keeps the banner
 *   useful for real errors.
 */
const BENIGN_ERROR_PATTERNS = [
  /ResizeObserver loop (completed with undelivered notifications|limit exceeded)/i,
];

function isBenign(message: string): boolean {
  return BENIGN_ERROR_PATTERNS.some((re) => re.test(message));
}

window.addEventListener("error", (event) => {
  if (isBenign(event.message)) return;
  const stack = (event.error as { stack?: string } | undefined)?.stack ?? "";
  const detail = `${event.message} @ ${event.filename}:${event.lineno}:${event.colno}\n${stack}`;
  showGlobalDebugBanner("ERROR", detail);
});

window.addEventListener("unhandledrejection", (event) => {
  const reason = event.reason as { message?: string; stack?: string } | string | undefined;
  const message =
    typeof reason === "string" ? reason : reason?.message ?? String(reason);
  if (isBenign(message)) return;
  const stack = typeof reason === "object" && reason ? reason?.stack ?? "" : "";
  showGlobalDebugBanner("REJECT", `${message}\n${stack}`);
});

const root = document.getElementById("root");

if (!root) {
  throw new Error("Missing #root container");
}

initializeTheme();

render(<App />, root);
bootWindow.nativeTelemetry?.emit("main-script-rendered", {
  childElementCount: root.childElementCount
});

function currentInteractiveRoute(): string {
  if (window.location.protocol === "file:") {
    return appShell.currentRoute.value;
  }

  return `${window.location.pathname}${window.location.search}`;
}

function scheduleInteractiveMarker(): void {
  const emit = () => {
    reportInteractive(currentInteractiveRoute());
    markAppBootedAfterInteractive();
  };

  requestAnimationFrame(() => {
    requestAnimationFrame(emit);
  });
  window.setTimeout(emit, 320);
  window.setTimeout(emit, 1500);
}

scheduleInteractiveMarker();
