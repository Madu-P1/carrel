import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { AskView } from "@/features/ask/AskView";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { LibraryView } from "@/features/library/LibraryView";
import { NotFoundView } from "@/features/NotFoundView";
import { ReaderView } from "@/features/reader/ReaderView";
import { SessionView } from "@/features/session/SessionView";
import { StudyView } from "@/features/study/StudyView";

import { appShell } from "./shell/useAppShell";
import { AppShell, BundledAppShell } from "./shell/AppShell";

function parseBundledRoute(path: string): URL {
  // Default landing is the Dashboard. Historically this defaulted to
  // /library; changed when the Dashboard home landed.
  return new URL(path || "/", "https://einstein.local");
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
    return <ReaderView chunkId={bundledReaderChunkId(rawPath)} id={bundledReaderId(rawPath)} />;
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

  if (path.startsWith("/session")) {
    return <SessionView />;
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
          <Route component={NotFoundView} default />
        </Router>
      </AppShell>
    </LocationProvider>
  );
}
