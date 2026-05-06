import { useRef } from "preact/hooks";

/**
 * Map a path to a stable ordinal so we can decide whether the user is
 * navigating "forward" (deeper into the app) or "backward" (toward the
 * dashboard). The order matches the sidebar nav order — Dashboard at 0,
 * Plan at the end, unknown routes pushed past the last known.
 */
function routeMotionIndex(path: string): number {
  if (path === "/") return 0;
  if (path.startsWith("/session")) return 1;
  if (path.startsWith("/library")) return 2;
  if (path.startsWith("/reader")) return 3;
  if (path.startsWith("/ask")) return 4;
  if (path.startsWith("/study")) return 5;
  if (path.startsWith("/search")) return 6;
  if (path.startsWith("/concepts")) return 7;
  if (path.startsWith("/plan")) return 8;
  return 9;
}

/**
 * Return the direction the user just navigated, used to drive the
 * page-transition CSS class. Holds the previous path/index in refs so
 * re-renders without a path change return the same value.
 */
export function useRouteMotion(pathname: string): "backward" | "forward" | "none" {
  const previousPathRef = useRef(pathname);
  const previousIndexRef = useRef(routeMotionIndex(pathname));
  const motionRef = useRef<"backward" | "forward" | "none">("none");

  if (previousPathRef.current !== pathname) {
    const nextIndex = routeMotionIndex(pathname);
    if (nextIndex > previousIndexRef.current) {
      motionRef.current = "forward";
    } else if (nextIndex < previousIndexRef.current) {
      motionRef.current = "backward";
    } else {
      motionRef.current = "none";
    }
    previousPathRef.current = pathname;
    previousIndexRef.current = nextIndex;
  }

  return motionRef.current;
}
