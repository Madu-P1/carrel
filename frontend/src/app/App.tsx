import type { ComponentChildren, FunctionComponent } from "preact";
import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { NotFoundView } from "@/features/NotFoundView";

import { lazyRoute } from "./lazyRoute";
import { AppShell, BundledAppShell } from "./shell/AppShell";
import { appShell } from "./shell/useAppShell";

/*
 * Code-splitting strategy
 * -----------------------
 *
 * The Dashboard is the home page — eagerly imported so the first paint
 * has zero waterfall. Every other route is lazy via `lazyRoute()`,
 * which is a signal-backed alternative to preact/compat's `lazy()` +
 * `Suspense`.
 *
 * Why not Suspense? Perf ship 7ac8931 briefly route-split Reader via
 * `lazy()` + `Suspense`. Under the bundled file:// macOS shell, the
 * chunk fetched fine (verified in WebKit's resource log) but the
 * Suspense re-render path silently failed: the boundary stayed in its
 * pending state, the page rendered blank, no error. preact/compat's
 * Suspense has known edge cases in the no-server / file-protocol /
 * inlined-entry combination.
 *
 * lazyRoute() sidesteps Suspense by writing the loaded component into a
 * Preact signal. Signals trigger re-renders directly when their value
 * changes, no render-time tree-magic involved. The build script's
 * dynamic-chunk path rewrite (build-macos.mjs) already routes
 * `import("./X.js")` calls to assets.new/X.js, so chunks resolve
 * correctly under file:// without further work.
 */

const SessionView = lazyRoute(
  () => import("@/features/session/SessionView").then((m) => ({ default: m.SessionView })),
  { displayName: "SessionView" }
);
const LibraryView = lazyRoute(
  () => import("@/features/library/LibraryView").then((m) => ({ default: m.LibraryView })),
  { displayName: "LibraryView" }
);
const ReaderView = lazyRoute(
  () => import("@/features/reader/ReaderView").then((m) => ({ default: m.ReaderView })),
  { displayName: "ReaderView" }
);
const AskView = lazyRoute(
  () => import("@/features/ask/AskView").then((m) => ({ default: m.AskView })),
  { displayName: "AskView" }
);
const StudyView = lazyRoute(
  () => import("@/features/study/StudyView").then((m) => ({ default: m.StudyView })),
  { displayName: "StudyView" }
);
const SearchView = lazyRoute(
  () => import("@/features/search/SearchView").then((m) => ({ default: m.SearchView })),
  { displayName: "SearchView" }
);
const ConceptGraphView = lazyRoute(
  () => import("@/features/concepts/ConceptGraphView").then((m) => ({ default: m.ConceptGraphView })),
  { displayName: "ConceptGraphView" }
);
const PlanView = lazyRoute(
  () => import("@/features/plan/PlanView").then((m) => ({ default: m.PlanView })),
  { displayName: "PlanView" }
);

interface AppShellChildProps {
  rawPath: string;
}

interface RouteEntry {
  /** Browser-mode pattern for `<Route path>`. Empty string means
   *  this entry is bundled-only (e.g., the dashboard fallback). */
  pattern: string;
  /** Bundled-mode prefix tested against `parseBundledRoute(...).pathname`.
   *  Null means "default fallback if nothing else matched". */
  bundledPrefix: string | null;
  Component: FunctionComponent<AppShellChildProps>;
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
  // ROUTES is a non-empty const array; the last entry is the dashboard
  // fallback so this lookup is always defined.
  const entry = matched ?? ROUTES[ROUTES.length - 1]!;
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
