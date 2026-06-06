import { ErrorBoundary, ToastHost } from "@/design-system";
import { appShell, pathnameFromRoute, setCurrentRoute } from "@/app/shell/useAppShell";
import { ShelfView } from "@/features/shelf/ShelfView";
import { VerifyView } from "@/features/verify/VerifyView";

import styles from "./cachet.module.css";

/**
 * The standalone Cachet shell (demo skeleton).
 *
 * Cachet is NOT Carrel with a Verify tab: this shell hosts only the
 * verification surfaces (Verify, Shelf). It bypasses the study AppShell and its
 * sidebar entirely, and reuses the existing `appShell.currentRoute` signal as
 * its nav (no router registered, so a plain `setCurrentRoute` drives it). That
 * makes the Shelf -> Verify "open a saved record" hand-off work for free, the
 * same under http (Vite dev) and file:// (bundled app).
 *
 * Deliberately minimal: it mounts the current, on-main VerifyView/ShelfView
 * (with the current engine), so it carries no dependency on the stale
 * cachet-extraction shell. The richer shell (sources picker, command palette,
 * the host-agnostic VerifyView props) layers in additively on top of this.
 */

function briefFromRoute(route: string): string | null {
  try {
    return new URL(route, "https://cachet.local").searchParams.get("brief");
  } catch {
    return null;
  }
}

export function CachetApp() {
  const route = appShell.currentRoute.value;
  const onShelf = pathnameFromRoute(route).startsWith("/shelf");
  const brief = briefFromRoute(route);

  return (
    <ErrorBoundary>
      <div className={styles.shell}>
        <header className={styles.bar}>
          <span className={styles.wordmark}>Cachet</span>
          <nav className={styles.nav} aria-label="Cachet sections">
            <button
              type="button"
              className={onShelf ? styles.navItem : styles.navItemActive}
              aria-current={onShelf ? undefined : "page"}
              onClick={() => setCurrentRoute("/verify")}
            >
              Verify
            </button>
            <button
              type="button"
              className={onShelf ? styles.navItemActive : styles.navItem}
              aria-current={onShelf ? "page" : undefined}
              onClick={() => setCurrentRoute("/shelf")}
            >
              Shelf
            </button>
          </nav>
        </header>
        <main className={styles.canvas}>
          {onShelf ? <ShelfView /> : <VerifyView key={brief ?? "live"} briefId={brief} />}
        </main>
      </div>
      <ToastHost />
    </ErrorBoundary>
  );
}
