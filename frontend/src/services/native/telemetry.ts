declare global {
  interface Window {
    __einsteinInteractiveReported?: boolean;
    __einsteinInteractivePayload?: {
      perfNowMs: number;
      route: string;
    };
    nativeTelemetry?: {
      emit: (event: string, payload?: Record<string, unknown>) => void;
    };
  }
}

export function reportInteractive(route: string): void {
  if (window.__einsteinInteractiveReported) {
    return;
  }

  window.__einsteinInteractiveReported = true;
  performance.mark("app-interactive");
  window.__einsteinInteractivePayload = {
    route,
    perfNowMs: performance.now()
  };
  window.nativeTelemetry?.emit("app-interactive", window.__einsteinInteractivePayload);
}
