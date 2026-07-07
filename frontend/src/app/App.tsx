import { LocationProvider, Route, Router, useLocation } from "preact-iso";

import { ErrorBoundary } from "@/design-system";
import { DemoPage } from "@/design-system/__demo__/DemoPage";
import { VerifyView } from "@/features/verify/VerifyView";
import { ShelfView } from "@/features/shelf/ShelfView";
import { LibraryView } from "@/features/library/LibraryView";
import { NotFoundView } from "@/features/NotFoundView";
import { ReaderView } from "@/features/reader/ReaderView";

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
  // Default landing is the Library — the vault/upload surface that feeds
  // Verify. (The study-era Dashboard home was removed with the Carrel
  // extraction; Codex is Cachet's home.)
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

function bundledBriefId(path: string): string | null {
  return parseBundledRoute(path).searchParams.get("brief");
}

function bundledReaderNodeId(path: string): number | null {
  const raw = parseBundledRoute(path).searchParams.get("node");
  if (raw === null || raw === "") return null;
  const parsed = Number(raw);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
}

function _parseQueryNodeId(value: unknown): number | null {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : null;
}

function BrowserReaderRoute({ id }: { id?: string }) {
  const { query } = useLocation();

  return (
    <ReaderView
      chunkId={query.chunk ?? null}
      nodeId={_parseQueryNodeId(query.node)}
      id={id}
    />
  );
}

function BrowserVerifyRoute() {
  const { query } = useLocation();
  // `?brief=ID` re-hydrates the Verify view from a saved brief (Shelf -> open).
  // Nullish-coalesce so an absent param is null (not undefined), matching the
  // effect's `if (!briefId) return` guard. preact-iso re-renders this wrapper in
  // place on a query-only change, so KEY VerifyView on the brief id: a
  // brief -> brief (or brief -> live) switch remounts it and re-reads the cert
  // seal seed instead of holding the prior brief's stale one.
  const brief = query.brief ?? null;
  return <VerifyView key={brief ?? "live"} briefId={brief} />;
}

function renderBundledRoute(rawPath: string) {
  const path = parseBundledRoute(rawPath).pathname;

  if (path.startsWith("/reader")) {
    return (
      <ReaderView
        chunkId={bundledReaderChunkId(rawPath)}
        nodeId={bundledReaderNodeId(rawPath)}
        id={bundledReaderId(rawPath)}
      />
    );
  }

  if (path.startsWith("/verify")) {
    // Key on the brief id so switching briefs (or brief -> live) remounts the
    // verify subtree, re-reading the cert seal seed instead of keeping a stale one.
    const brief = bundledBriefId(rawPath);
    return <VerifyView key={brief ?? "live"} briefId={brief} />;
  }

  if (path.startsWith("/shelf")) {
    return <ShelfView />;
  }

  // Default landing is the Library — the vault/upload surface feeding Verify.
  return <LibraryView />;
}

/*
 * BoundedRoutes wraps the preact-iso Router in an ErrorBoundary keyed by
 * the current path, so a render throw inside one feature does not blank
 * the AppShell chrome (sidebar, header, etc. stay alive). The boundary
 * auto-resets when the user navigates, so a broken Reader doesn't trap
 * the user on the error screen forever.
 *
 * Per the preact/compat Suspense/lazy gotcha (see CLAUDE.md), this is a
 * plain class-component boundary, not a Suspense boundary.
 */
function BoundedRoutes() {
  const { path } = useLocation();
  return (
    <ErrorBoundary resetKey={path}>
      <Router>
        <Route component={LibraryView} path="/" />
        <Route component={LibraryView} path="/library" />
        <Route component={BrowserReaderRoute} path="/reader/:id?" />
        <Route component={BrowserVerifyRoute} path="/verify" />
        <Route component={ShelfView} path="/shelf" />
        <Route component={NotFoundView} default />
      </Router>
    </ErrorBoundary>
  );
}

export function App() {
  const params = new URLSearchParams(window.location.search);
  const isDemo = params.get("design") === "1";
  const isBundledMode = window.location.protocol === "file:";

  if (isDemo) {
    return <DemoPage />;
  }

  if (isBundledMode) {
    const route = appShell.currentRoute.value;
    return (
      <BundledAppShell>
        <ErrorBoundary resetKey={route}>
          {renderBundledRoute(route)}
        </ErrorBoundary>
      </BundledAppShell>
    );
  }

  return (
    <LocationProvider>
      <AppShell>
        <BoundedRoutes />
      </AppShell>
    </LocationProvider>
  );
}
