import { useEffect, useRef, useState } from "preact/hooks";

import { ErrorBoundary, ToastHost } from "@/design-system";
import { appShell, navigateTo, pathnameFromRoute } from "@/app/shell/useAppShell";
import { VerifyResults } from "@/features/verify/VerifyResults";
import { useVerify } from "@/features/verify/useVerify";
import verifyStyles from "@/features/verify/VerifyView.module.css";
import { ShelfView } from "@/features/shelf/ShelfView";

import { CommandPalette } from "./CommandPalette";
import { buildCommands } from "./commands";
import { enterRoom } from "./roomMotion";
import { CachetRail } from "./CachetRail";
import { DocumentExamination } from "./examine/DocumentExamination";
import { LecternView } from "./LecternView";
import { SealBenchView } from "@/features/attest/SealBenchView";
import { VaultView } from "./VaultView";
import { SettingsView } from "./SettingsView";
import styles from "./cachet.module.css";

/**
 * The Cachet shell. A quiet frame around a single document under examination:
 * a thin left rail and a canvas that fills the rest. It reuses the existing
 * appShell.currentRoute signal as its nav (no router registered, so navigateTo
 * falls back to setCurrentRoute), which makes the Shelf -> open-brief flow work
 * for free and works identically under http (Vite dev) and file:// (bundled .app).
 *
 * Cachet is NOT Carrel with a Verify tab. The lectern (the landing) IS the verify
 * surface: you paste, attach a record, and the verdict unfolds in place. The only
 * other verify route is the saved-brief reader (`/verify?brief=<id>`), opened from
 * the Shelf.
 */

function briefFromRoute(route: string): string | null {
  try {
    return new URL(route, "https://cachet.local").searchParams.get("brief");
  } catch {
    return null;
  }
}

/**
 * Saved-brief reader. Opening a brief from the Shelf re-hydrates the stored
 * verdict with NO re-verify and shows it read-only: the document (with its margin
 * annotations) and the verdict live inside the shared `VerifyResults`, so this is
 * a thin frame around it. The draft is not editable here; to re-check, start from
 * the lectern.
 */
function BriefReader({ briefId }: { briefId: string }) {
  const engine = useVerify({ briefId });
  const draft = engine.hydratedDraft ?? engine.response?.draft_text ?? "";
  return (
    <section className={styles.reader}>
      <button type="button" className={styles.readerBack} onClick={() => navigateTo("/shelf")}>
        ← Back to the Shelf
      </button>
      <div className={[styles.lecternVerdict, verifyStyles.verifyScope].join(" ")}>
        <VerifyResults engine={engine} draft={draft} />
      </div>
    </section>
  );
}

/** Top-strip eyebrow + helper per surface (handoff §2). */
function routeStrip(path: string): [string, string] {
  if (path.startsWith("/bench")) return ["Seal Bench", "Verify any Cachet certificate. No backend, no trust."];
  if (path.startsWith("/shelf")) return ["Shelf", "Saved briefs and their seals."];
  if (path.startsWith("/vault"))
    return ["Vault", "The sources a draft is checked against. Nothing leaves this machine."];
  if (path.startsWith("/settings")) return ["Settings", ""];
  return ["Lectern", "Paste a draft. Watch every claim get checked."];
}

function renderRoute(route: string) {
  const path = pathnameFromRoute(route);

  if (path.startsWith("/verify")) {
    // A saved brief opens read-only; bare /verify (no brief) is the live surface,
    // which is the lectern.
    const briefId = briefFromRoute(route);
    return briefId ? <BriefReader briefId={briefId} /> : <LecternView />;
  }
  if (path.startsWith("/bench")) {
    return <SealBenchView />;
  }
  if (path.startsWith("/shelf")) {
    return <ShelfView />;
  }
  if (path.startsWith("/vault")) {
    return <VaultView />;
  }
  if (path.startsWith("/settings")) {
    return <SettingsView />;
  }
  // The lectern is the landing and the live verify surface.
  return <LecternView />;
}

export function CachetApp() {
  const route = appShell.currentRoute.value;
  const path = pathnameFromRoute(route);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const canvasRef = useRef<HTMLElement | null>(null);
  const roomRef = useRef<HTMLDivElement | null>(null);
  const prevPath = useRef<string | null>(null);

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

  // Room handoff: the canvas persists across the unmount-on-nav route swap, so
  // without this a room opens scrolled to wherever the LAST room left off and
  // focus stays on a control that no longer exists. On every path change:
  // scroll home, settle the new room in (WAAPI, reduced-motion aware), and move
  // focus to the canvas so keyboard and screen-reader users land where the eye
  // does. The room is a `key`ed wrapper (roomRef), so it is a single stable
  // element per route that the room's own internal re-renders never replace,
  // which the entrance animation needs to target reliably. Skipped on first
  // paint (never steal the initial focus).
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    // Only on a genuine route CHANGE, never on the initial mount (prevPath is
    // null then) and never on a re-render that leaves the path unchanged. A
    // path-comparison guard is correct even when the initial route settles over
    // more than one render, which a simple first-paint flag mis-handled.
    const changed = prevPath.current !== null && prevPath.current !== path;
    prevPath.current = path;
    if (!changed) return;
    canvas.scrollTop = 0;
    enterRoom(roomRef.current);
    canvas.focus?.({ preventScroll: true });
  }, [path]);

  const [stripTitle, stripSub] = routeStrip(path);

  return (
    <div className={styles.app}>
      <CachetRail currentPath={path} />
      <div className={styles.mainCol}>
        <header className={styles.topStrip}>
          <h1 className={styles.topStripTitle}>{stripTitle}</h1>
          {stripSub ? <span className={styles.topStripSub}>{stripSub}</span> : null}
          <span className={styles.topStripMeta}>local corpus 2025.11 · network: none</span>
        </header>
        <main className={styles.canvas} ref={canvasRef} tabIndex={-1}>
          <ErrorBoundary resetKey={route}>
            <div key={path} ref={roomRef} className={styles.room}>
              {renderRoute(route)}
            </div>
          </ErrorBoundary>
        </main>
      </div>
      {paletteOpen ? (
        <CommandPalette
          commands={buildCommands(path, () => setPaletteOpen(false))}
          onClose={() => setPaletteOpen(false)}
        />
      ) : null}
      {/* Mounted at the shell level (not inside a routed view) so an open
          record survives the unmount-on-nav route swap above. */}
      <DocumentExamination />
      <ToastHost />
    </div>
  );
}
