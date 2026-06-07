import { useEffect, useState } from "preact/hooks";

import { ErrorBoundary, ToastHost } from "@/design-system";
import { appShell, navigateTo, pathnameFromRoute } from "@/app/shell/useAppShell";
import { VerifyView } from "@/features/verify/VerifyView";
import { ShelfView } from "@/features/shelf/ShelfView";

import { CommandPalette } from "./CommandPalette";
import { buildCommands } from "./commands";
import { CachetRail } from "./CachetRail";
import { LecternView } from "./LecternView";
import { SourcesView } from "./SourcesView";
import { SettingsView } from "./SettingsView";
import { liveDraft } from "./liveDraft";
import { takePendingDraft } from "./pendingDraft";
import { clearSource, loadedSource, refreshSources, setActiveRecord, sourceDocs } from "./source";
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
 * Verify station. Seeds the draft from a lectern hand-off (consumed once) or the
 * shared live draft (`liveDraft`), and writes every edit back so leaving and
 * returning to Verify keeps the draft. The live draft is shared with the lectern,
 * so a paste on the home page survives navigation too. A reopened brief (briefId
 * set) hydrates from the saved brief instead and is never persisted to the live
 * draft.
 */
function VerifyStation({ briefId }: { briefId: string | null }) {
  const [seed] = useState(() => (briefId ? null : takePendingDraft()));
  const docs = sourceDocs.value;
  const active = loadedSource.value;

  // The deterministic quote check needs the doc id of the record to check
  // against. Load the record list so the picker is populated even when the user
  // came straight to Verify, and let them choose which record is active here so
  // the check never silently runs with no source.
  useEffect(() => {
    void refreshSources();
    // A lectern hand-off persists immediately, so navigating away before typing
    // does not lose it.
    if (seed) liveDraft.value = seed;
  }, [seed]);

  return (
    <>
      <div className={styles.recordBar}>
        <span className={styles.recordBarLabel}>Checking against</span>
        <select
          className={styles.recordBarSelect}
          value={active?.docId ?? ""}
          onChange={(e) => {
            const id = (e.target as HTMLSelectElement).value;
            const doc = (docs ?? []).find((d) => d.id === id);
            if (doc) setActiveRecord(doc);
            else clearSource();
          }}
        >
          <option value="">No record loaded — choose one</option>
          {(docs ?? []).map((d) => (
            <option key={d.id} value={d.id}>
              {d.filename}
            </option>
          ))}
        </select>
        {active ? null : (
          <span className={styles.recordBarHint}>Add a record in Sources, then pick it here.</span>
        )}
      </div>
      {/* A refusal's "give Cachet what it needs" action routes to Sources, where the
          user loads the record the draft relies on. The shared verify surface stays
          host-agnostic; the record picker above lives in the Cachet shell. */}
      <VerifyView
        key={briefId ?? "live"}
        briefId={briefId}
        initialDraft={briefId ? seed : (seed ?? liveDraft.value)}
        // Auto-run only on a genuine lectern hand-off (a fresh pending draft was
        // consumed), never on a plain return to /verify. Without this guard, the
        // persisted live draft would make the station re-verify on every visit.
        autoRun={!briefId && seed !== null}
        onDraftChange={briefId ? undefined : (v) => (liveDraft.value = v)}
        onResolve={() => navigateTo("/sources")}
        headerTitle="Check the AI's read of your contract."
        headerSubtitle="Paste what an assistant told you about the document. Cachet checks every quoted clause against the record you loaded, on this device."
        samplePlaceholder="The agreement caps the supplier’s total liability at “£250,000” and renews automatically for successive 12-month terms unless either party gives 90 days’ written notice."
        docIds={active?.docId ? [active.docId] : undefined}
      />
    </>
  );
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
