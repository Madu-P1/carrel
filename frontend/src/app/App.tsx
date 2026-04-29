import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { AskView } from "@/features/ask/AskView";
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

function BrowserReaderRoute({ id }: { id?: string }) {
  const { query } = useLocation();

  return <ReaderView chunkId={query.chunk ?? null} id={id} />;
}

function renderBundledRoute(rawPath: string) {
  const path = parseBundledRoute(rawPath).pathname;

  if (path.startsWith("/reader")) {
    return (
      <ReaderView
        chunkId={bundledReaderChunkId(rawPath)}
        id={bundledReaderId(rawPath)}
      />
    );
  }

  if (path.startsWith("/ask")) {
    return <AskView />;
  }

  if (path.startsWith("/study")) {
    return <StudyView />;
  }

  if (path.startsWith("/library")) {
    return <LibraryView />;
  }

  if (path.startsWith("/search")) {
    return <SearchView />;
  }

  if (path.startsWith("/session")) {
    return <SessionView />;
  }

  if (path.startsWith("/plan")) {
    return <PlanView />;
  }

  // Default landing is the Dashboard — the legacy home the user asked for,
  // rebuilt on the new frontend.
  return <DashboardView />;
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
          <Route component={DashboardView} path="/" />
          <Route component={SessionView} path="/session" />
          <Route component={LibraryView} path="/library" />
          <Route component={BrowserReaderRoute} path="/reader/:id?" />
          <Route component={AskView} path="/ask" />
          <Route component={StudyView} path="/study" />
          <Route component={SearchView} path="/search" />
          <Route component={PlanView} path="/plan" />
          <Route component={NotFoundView} default />
        </Router>
      </AppShell>
    </LocationProvider>
  );
}
