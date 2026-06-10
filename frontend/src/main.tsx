import { render } from "preact";

import { App } from "./app/App";
import { CachetApp } from "./cachet/CachetApp";
import { markAppBootedAfterInteractive } from "./app/shell/boot";
import { appShell, initializeTheme } from "./app/shell/useAppShell";
import { reportInteractive } from "./services/native/telemetry";
import "./main.css";
// Stillwater tokens are loaded globally because the Notes rail content
// renders in two places (NotesPage's main pane + the AppShell sidebar
// when isNotesRailActive). Both ancestors set data-stillwater="true"
// to load these vars.
import "./features/notes/notes-tokens.css";

const bootWindow = window as typeof window & {
  nativeTelemetry?: { emit: (event: string, payload?: Record<string, unknown>) => void };
  __einsteinMainStarted?: boolean;
};

bootWindow.__einsteinMainStarted = true;
bootWindow.nativeTelemetry?.emit("main-script-start", {
  href: window.location.href
});

// DEV-ONLY DEBUG: surface any uncaught JS error or rejected promise as a
// fixed red banner pinned to the top of the page. Lets us debug the
// blank-Reader class of issue without WKWebView devtools open. Gated on
// import.meta.env.DEV (statically compiled out of production builds): a
// production user must never get a raw stack trace painted in alarm red
// over the app because some benign rejection escaped.
if (import.meta.env.DEV) {
  const showGlobalDebugBanner = (prefix: string, info: string) => {
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
  };

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

  const isBenign = (message: string): boolean =>
    BENIGN_ERROR_PATTERNS.some((re) => re.test(message));

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
}

const root = document.getElementById("root");

if (!root) {
  throw new Error("Missing #root container");
}

if (import.meta.env.VITE_CACHET_ONLY === "true") {
  // Cachet as its own product: paper always, only the verify/shelf surfaces, no
  // study chrome. Default off, so an unset flag leaves the study app unchanged.
  document.documentElement.classList.remove("theme-dark");
  document.documentElement.classList.add("theme-light");
  // The tab title is "Einstein" in index.html (the study app's legacy name).
  // Cachet is its own product, so name the window for it. Cachet build only;
  // the study app keeps its title.
  document.title = "Cachet";
  render(<CachetApp />, root);
} else {
  initializeTheme();
  render(<App />, root);
}
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
