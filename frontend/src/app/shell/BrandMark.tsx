import { useState } from "preact/hooks";
import type { JSX } from "preact";

import styles from "./BrandMark.module.css";

/**
 * Brand tile that sits at the top-left of every view.
 *
 * Uses `frontend/src/assets/logo.png` via a Vite URL import. If the file is
 * missing (image load fails), we fall back to a text monogram so the shell
 * still reads coherently during development before the asset is dropped in.
 *
 * Sized intentionally to match the height of the two-line title to its
 * right (h2 + caption ≈ 44px). Squircle clip mirrors macOS app-icon masking.
 *
 * Optionally interactive: pass `onClick` and the mark renders as a real
 * <button>, with hover/focus styling. The sidebar uses this to make the
 * icon itself the "collapse sidebar" control — no extra chrome needed.
 */
// Vite resolves this import to a URL at build time. When the file is
// missing, the build would fail — so we try/catch via a URL constructor
// pattern instead. Simpler: a static import with `?url` suffix and a
// runtime onError handler.
import logoUrl from "@/assets/logo.png?url";

interface BrandMarkProps {
  /** Optional click handler. When provided, the mark renders as an
   *  interactive <button> with hover/focus affordances. */
  onClick?: (event: JSX.TargetedMouseEvent<HTMLButtonElement>) => void;
  /** Accessible label when interactive. Defaults to "Einstein Tutor". */
  ariaLabel?: string;
  /** Tooltip on hover. Useful for conveying the click action ("Toggle
   *  sidebar"). */
  title?: string;
}

export function BrandMark({ onClick, ariaLabel, title }: BrandMarkProps = {}) {
  const [showFallback, setShowFallback] = useState(false);

  const visual = showFallback ? (
    <span className={styles.fallbackMark}>ET</span>
  ) : (
    <img
      src={logoUrl}
      alt="Einstein Tutor"
      className={styles.markImage}
      width={44}
      height={44}
      draggable={false}
      onError={() => setShowFallback(true)}
      onLoad={(event) => {
        // A 1×1 placeholder PNG ships with the repo so the build never
        // fails when the real logo hasn't been dropped in yet. Detect
        // the placeholder at runtime by its intrinsic dimensions and
        // swap to the text monogram — keeps the topbar looking
        // intentional during development instead of a blank navy tile.
        const img = event.currentTarget as HTMLImageElement;
        if (img.naturalWidth <= 4 && img.naturalHeight <= 4) {
          setShowFallback(true);
        }
      }}
    />
  );

  const frameClass = [
    styles.mark,
    showFallback ? styles.fallback : "",
    onClick ? styles.interactive : ""
  ]
    .filter(Boolean)
    .join(" ");

  if (onClick) {
    return (
      <button
        type="button"
        className={frameClass}
        onClick={onClick}
        aria-label={ariaLabel ?? "Einstein Tutor"}
        title={title}
      >
        {visual}
      </button>
    );
  }

  return (
    <div className={frameClass} aria-label={ariaLabel ?? "Einstein Tutor"}>
      {visual}
    </div>
  );
}
