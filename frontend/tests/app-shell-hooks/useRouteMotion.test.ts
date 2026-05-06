import { renderHook } from "@testing-library/preact";
import { expect, test } from "vitest";

import { useRouteMotion } from "../../src/app/shell/hooks/useRouteMotion";

/**
 * useRouteMotion derives a "forward" / "backward" / "none" direction so the
 * page-transition layer can pick the right CSS class. Index ordering matches
 * the sidebar nav: "/" = 0, /session = 1, /library = 2, /reader = 3,
 * /ask = 4, /study = 5, /search = 6, /concepts = 7, /plan = 8.
 */

test("returns 'none' on first render with the same path", () => {
  const { result, rerender } = renderHook(({ path }) => useRouteMotion(path), {
    initialProps: { path: "/" }
  });

  expect(result.current).toBe("none");

  // Rerender with the same path — nothing changes, motion stays "none".
  rerender({ path: "/" });
  expect(result.current).toBe("none");
});

test("returns 'forward' when path moves to a higher-index route", () => {
  const { result, rerender } = renderHook(({ path }) => useRouteMotion(path), {
    initialProps: { path: "/" }
  });

  expect(result.current).toBe("none");

  // "/" (index 0) -> "/library" (index 2) is forward.
  rerender({ path: "/library" });
  expect(result.current).toBe("forward");

  // "/library" (index 2) -> "/ask" (index 4) is also forward.
  rerender({ path: "/ask" });
  expect(result.current).toBe("forward");
});

test("returns 'backward' when path moves to a lower-index route", () => {
  const { result, rerender } = renderHook(({ path }) => useRouteMotion(path), {
    initialProps: { path: "/concepts" }
  });

  // First render against /concepts (index 7) is "none".
  expect(result.current).toBe("none");

  // /concepts (7) -> "/" (0) is backward.
  rerender({ path: "/" });
  expect(result.current).toBe("backward");
});
