export function isColdBootMotionEnabled(): boolean {
  return typeof document !== "undefined" && document.body.getAttribute("data-app-booted") !== "true";
}

export function markAppBootedAfterInteractive(): void {
  requestAnimationFrame(() => {
    window.setTimeout(() => {
      document.body.setAttribute("data-app-booted", "true");
    }, 120);
  });
}
