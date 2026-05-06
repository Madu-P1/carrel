import type { JSX } from "preact";
import { useState } from "preact/hooks";

import logoUrl from "@/assets/logo.png?url";

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

interface BrandMarkProps {
  /** Optional click handler. When provided, the mark renders as an
   *  interactive <button> with hover/focus affordances. */
  onClick?: (event: JSX.TargetedMouseEvent<HTMLButtonElement>) => void;
  /** Accessible label when interactive. Defaults to "Carrel". */
  ariaLabel?: string;
  /** Tooltip on hover. Useful for conveying the click action ("Toggle
   *  sidebar"). */
  title?: string;
}

export function BrandMark({ onClick, ariaLabel, title }: BrandMarkProps = {}) {
  const [showFallback, setShowFallback] = useState(false);

  const visual = showFallback ? (
    // Two-letter monogram fallback when the logo asset is missing or is
    // still the placeholder. Matches the form of the existing PNG mark
    // ("ET" two-letter monogram on dark navy). Swap to the actual Carrel
    // logo asset and this fallback only renders during dev before the
    // image lands.
    <span className={styles.fallbackMark}>Cr</span>
  ) : (
    <img
      src={logoUrl}
      alt="Carrel"
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
        aria-label={ariaLabel ?? "Carrel"}
        title={title}
      >
        {visual}
      </button>
    );
  }

  return (
    <div className={frameClass} aria-label={ariaLabel ?? "Carrel"}>
      {visual}
    </div>
  );
}
