import { ComponentChildren } from "preact";

export interface LoadingBoundaryProps {
  /** Render the fallback when true; render children when false. */
  loading: boolean;
  /** Node shown while `loading` is true. Use a `<Skeleton>` or `<Spinner>`. */
  fallback: ComponentChildren;
  children: ComponentChildren;
}

/**
 * Pure props-based loading scope: render fallback while `loading` is
 * true, render children otherwise. Imported from Next.js App Router's
 * `loading.tsx` convention (every route/panel has its own bounded
 * fallback), but deliberately without `Suspense`. `preact/compat`
 * `Suspense` + `lazy()` is broken under `file://` (see CLAUDE.md).
 *
 * If you want a delayed or min-duration fallback (to avoid flicker on
 * sub-100ms loads), wrap the prop in your own hook before passing it
 * in. Keeping this primitive trivial means it composes cleanly with
 * signals, useState, and SWR-style stores.
 */
export function LoadingBoundary({ loading, fallback, children }: LoadingBoundaryProps) {
  return <>{loading ? fallback : children}</>;
}
