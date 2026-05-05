import type { ComponentChildren, FunctionComponent } from "preact";
import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { AskView } from "@/features/ask/AskView";
import { ConceptGraphView } from "@/features/concepts/ConceptGraphView";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { LibraryView } from "@/features/library/LibraryView";
import { NotFoundView } from "@/features/NotFoundView";
import { PlanView } from "@/features/plan/PlanView";
import { ReaderView } from "@/features/reader/ReaderView";
import { SearchView } from "@/features/search/SearchView";
import { SessionView } from "@/features/session/SessionView";
import { StudyView } from "@/features/study/StudyView";

import { appShell } from "./shell/useAppShell";
import { AppShell, BundledAppShell } from "./shell/AppShell";

/*
 * Reader was briefly route-split via `lazy()` + `Suspense` from
 * preact/compat (perf ship 7ac8931). Under the bundled file:// macOS
 * shell that combination produced a blank Reader pane: the chunk
 * fetched successfully (verified via WebKit's resource log) but the
 * Suspense + lazy resolution didn't re-render the tree. preact/compat's
 * Suspense has known limitations in this combination of
 * server-less / file-protocol / inlined-entry that we don't have time
 * to chase down here. Reverted to a static import so Reader renders
 * reliably. Cold-start cost is only ~10 KB gz (under file:// load,
 * imperceptible) — not worth a broken page.
 *
 * The build script's chunk-path rewrite stays in place for any future
 * code split that doesn't go through preact/compat's Suspense (e.g., a
 * truly optional feature gated behind a user action, where loading is
 * triggered by user click rather than a render-time Suspense boundary).
 */

interface RouteEntry {
  /** Browser-mode pattern for `<Route path>`. Empty string means
   *  this entry is bundled-only (e.g., the dashboard fallback). */
  pattern: string;
  /** Bundled-mode prefix tested against `parseBundledRoute(...).pathname`.
   *  Null means "default fallback if nothing else matched". */
  bundledPrefix: string | null;
  Component: FunctionComponent<{ rawPath: string }>;
}

function parseBundledRoute(path: string): URL {
  // Default landing is the Dashboard. Historically this defaulted to
  // /library; changed when the Dashboard home landed.
  return new URL(path || "/", "https://carrel.local");
}

function bundledReaderId(path: string): string | undefined {
  const match = parseBundledRoute(path).pathname.match(/^\/reader(?:\/([^/?#]+))?/);
  if (!match?.[1]) {
    return undefined;
  }

  try {
    return decodeURIComponent(match[1]);
  } catch {
    return match[1];
  }
}

function bundledReaderChunkId(path: string): string | null {
  return parseBundledRoute(path).searchParams.get("chunk");
}

/** Reader gets its own component because both renderers need to thread
 *  `id` and `chunkId` through. Browser mode uses `useLocation()` for
 *  the `?chunk=` query and accepts `id` as a route param from
 *  preact-iso (which auto-injects URL params as props). Bundled mode
 *  uses the raw appShell route since there's no LocationProvider. */
function BrowserReaderRoute({ id }: { id?: string }) {
  const { query } = useLocation();
  return <ReaderView chunkId={query.chunk ?? null} id={id} />;
}

function BundledReaderRoute({ rawPath }: { rawPath: string }) {
  return (
    <ReaderView
      chunkId={bundledReaderChunkId(rawPath)}
      id={bundledReaderId(rawPath)}
    />
  );
}

/**
 * Single source of truth for the route table. Both the bundled-mode
 * renderer and the LocationProvider `<Router>` read from this array,
 * so adding a route is one line in one place. (The audit flagged the
 * old hand-rolled if/else chain as a drift risk.)
 *
 * The Reader entry has two `Component`s under the hood — one for
 * each renderer — because the props plumbing differs.
 */
const ROUTES: RouteEntry[] = [
  { pattern: "/session", bundledPrefix: "/session", Component: () => <SessionView /> },
  { pattern: "/library", bundledPrefix: "/library", Component: () => <LibraryView /> },
  { pattern: "/reader/:id?", bundledPrefix: "/reader", Component: BundledReaderRoute },
  { pattern: "/ask", bundledPrefix: "/ask", Component: () => <AskView /> },
  { pattern: "/study", bundledPrefix: "/study", Component: () => <StudyView /> },
  { pattern: "/search", bundledPrefix: "/search", Component: () => <SearchView /> },
  { pattern: "/concepts", bundledPrefix: "/concepts", Component: () => <ConceptGraphView /> },
  { pattern: "/plan", bundledPrefix: "/plan", Component: () => <PlanView /> },
  { pattern: "/", bundledPrefix: null, Component: () => <DashboardView /> },
];

function renderBundledRoute(rawPath: string): ComponentChildren {
  const pathname = parseBundledRoute(rawPath).pathname;
  const matched = ROUTES.find((entry) =>
    entry.bundledPrefix !== null && pathname.startsWith(entry.bundledPrefix)
  );
  const entry = matched ?? ROUTES[ROUTES.length - 1];
  const Component = entry.Component;
  return <Component rawPath={rawPath} />;
}

export function App() {
  const params = new URLSearchParams(window.location.search);
  const isDemo = params.get("design") === "1";
  const isBundledMode = window.location.protocol === "file:";

  if (isDemo) {
    return <DemoPage />;
  }

  if (isBundledMode) {
    return <BundledAppShell>{renderBundledRoute(appShell.currentRoute.value)}</BundledAppShell>;
  }

  return (
    <LocationProvider>
      <AppShell>
        <Router>
          {ROUTES.filter((entry) => entry.pattern !== "/reader/:id?").map((entry) => (
            <Route key={entry.pattern} component={entry.Component} path={entry.pattern} />
          ))}
          <Route component={BrowserReaderRoute} path="/reader/:id?" />
          <Route component={NotFoundView} default />
        </Router>
      </AppShell>
    </LocationProvider>
  );
}
