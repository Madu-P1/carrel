import { beforeEach, describe, expect, it, vi } from "vitest";

import { reportInteractive } from "@/services/native/telemetry";

describe("reportInteractive", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    window.__einsteinInteractiveReported = false;
    window.nativeTelemetry = { emit: vi.fn() };
    vi.spyOn(performance, "mark");
  });

  it("emits the interactive mark only once", () => {
    reportInteractive("/library");
    reportInteractive("/reader/demo");

    expect(performance.mark).toHaveBeenCalledTimes(1);
    expect(window.nativeTelemetry?.emit).toHaveBeenCalledTimes(1);
    expect(window.nativeTelemetry?.emit).toHaveBeenCalledWith("app-interactive", {
      route: "/library",
      perfNowMs: expect.any(Number)
    });
  });
});
