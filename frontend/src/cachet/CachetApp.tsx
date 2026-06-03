import { useEffect, useState } from "preact/hooks";

import { ErrorBoundary, ToastHost } from "@/design-system";
import { appShell, pathnameFromRoute } from "@/app/shell/useAppShell";
import { VerifyView } from "@/features/verify/VerifyView";
import { ShelfView } from "@/features/shelf/ShelfView";

import { CommandPalette } from "./CommandPalette";
import { buildCommands } from "./commands";
import { CachetRail } from "./CachetRail";
import { LecternView } from "./LecternView";
import { SourcesView } from "./SourcesView";
import { SettingsView } from "./SettingsView";
import { takePendingDraft } from "./pendingDraft";
import { VerdictDemo } from "./__demo__/VerdictDemo";
import { StreamFlipDemo } from "./__demo__/StreamFlipDemo";
import styles from "./cachet.module.css";

/**
 * The Cachet shell. A quiet frame around a single document under examination:
 * a thin left rail and a canvas that fills the rest. It reuses the existing
 * appShell.currentRoute signal as its nav (no router registered, so navigateTo
 * falls back to setCurrentRoute), which makes the Shelf -> Verify open work for
 * free and works identically under http (Vite dev) and file:// (bundled .app).
 *
 * Cachet is NOT Carrel with a Verify tab. This shell hosts only the verification
 * surfaces (Verify, Shelf, Sources, Settings); the Carrel features are excluded.
 */

function briefFromRoute(route: string): string | null {
  try {
    return new URL(route, "https://cachet.local").searchParams.get("brief");
  } catch {
    return null;
  }
}

/**
 * Verify station. Consumes a lectern-seeded draft exactly once per mount (the
 * useState initializer runs once), so the user's paste on the lectern becomes
 * the verify. A reopened brief (briefId set) ignores any seed. CachetApp swaps
 * views by route, so leaving and returning to Verify remounts this and clears
 * any stale seed.
 */
function VerifyStation({ briefId }: { briefId: string | null }) {
  const [seed] = useState(() => (briefId ? null : takePendingDraft()));
  return <VerifyView key={briefId ?? "live"} briefId={briefId} initialDraft={seed} />;
}

function renderRoute(route: string) {
  const path = pathnameFromRoute(route);

  // Dev-only fixture harness for building/screenshotting the verdict moments
  // without a backend. cachet.html?demo=verdicts. Not part of the real flow.
  const demo = new URLSearchParams(window.location.search).get("demo");
  if (demo === "verdicts") {
    return <VerdictDemo />;
  }
  if (demo === "stream") {
    return <StreamFlipDemo />;
  }

  if (path.startsWith("/verify")) {
    return <VerifyStation briefId={briefFromRoute(route)} />;
  }
  if (path.startsWith("/shelf")) {
    return <ShelfView />;
  }
  if (path.startsWith("/sources")) {
    return <SourcesView />;
  }
  if (path.startsWith("/settings")) {
    return <SettingsView />;
  }
  // The lectern is the landing.
  return <LecternView />;
}

export function CachetApp() {
  const route = appShell.currentRoute.value;
  const path = pathnameFromRoute(route);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // SM-V7: ⌘K (or Ctrl+K) opens the command spine from anywhere in the shell.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setPaletteOpen((open) => !open);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <div className={styles.app}>
      <CachetRail currentPath={path} />
      <main className={styles.canvas}>
        <ErrorBoundary resetKey={route}>{renderRoute(route)}</ErrorBoundary>
      </main>
      {paletteOpen ? (
        <CommandPalette
          commands={buildCommands(path, () => setPaletteOpen(false))}
          onClose={() => setPaletteOpen(false)}
        />
      ) : null}
      <ToastHost />
    </div>
  );
}
