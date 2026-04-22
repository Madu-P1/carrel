import { render } from "preact";

import { App } from "./app/App";
import { markAppBootedAfterInteractive } from "./app/shell/boot";
import { appShell, initializeTheme } from "./app/shell/useAppShell";
import { reportInteractive } from "./services/native/telemetry";
import "./main.css";

const bootWindow = window as typeof window & {
  nativeTelemetry?: { emit: (event: string, payload?: Record<string, unknown>) => void };
  __einsteinMainStarted?: boolean;
};

bootWindow.__einsteinMainStarted = true;
bootWindow.nativeTelemetry?.emit("main-script-start", {
  href: window.location.href
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
  window.setTimeout(emit, 1500);
}

scheduleInteractiveMarker();
