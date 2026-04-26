import { lazy, Suspense } from "preact/compat";
import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { AskView } from "@/features/ask/AskView";
import { DashboardView } from "@/features/dashboard/DashboardView";
import { LibraryView } from "@/features/library/LibraryView";
import { NotFoundView } from "@/features/NotFoundView";
import { ReaderLoadingState } from "@/features/reader/components/ReaderLoadingState";
import { SessionView } from "@/features/session/SessionView";
import { StudyView } from "@/features/study/StudyView";

import { appShell } from "./shell/useAppShell";
import { AppShell, BundledAppShell } from "./shell/AppShell";

/*
 * Reader feature is route-split. It's the heaviest leaf in the app
 * (PdfToolbar, PdfViewer, PdfPage, OutlineRail, SourcePanel, the
 * usePdfDocument hook, plus the dynamic pdfjs-dist load that already
 * lives in lib/pdfjs-setup.ts) and most users land on Dashboard or
 * Library first. Splitting at the route boundary keeps the entry chunk
 * lean for cold starts; the Reader's own chunk loads on demand when
 * the user opens a document.
 *
 * `import().then(...default-shim)` bridges the named export to the
 * default export shape `lazy()` expects. Tests that import ReaderView
 * directly bypass this wrapper — they get the eager symbol from the
 * source path and never hit the Suspense boundary.
 */
const ReaderView = lazy(() =>
  import("@/features/reader/ReaderView").then((module) => ({
    default: module.ReaderView,
  }))
);

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

  return (
    <Suspense fallback={<ReaderLoadingState />}>
      <ReaderView chunkId={query.chunk ?? null} id={id} />
    </Suspense>
  );
}

function renderBundledRoute(rawPath: string) {
  const path = parseBundledRoute(rawPath).pathname;

  if (path.startsWith("/reader")) {
    return (
      <Suspense fallback={<ReaderLoadingState />}>
        <ReaderView
          chunkId={bundledReaderChunkId(rawPath)}
          id={bundledReaderId(rawPath)}
        />
      </Suspense>
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
