import { useEffect, useState } from "preact/hooks";

import styles from "./cachet.module.css";

/**
 * The splash (handoff §1): a full-screen dark plate. The open-ring mark draws
 * itself in (two arcs, staggered, cachetDraw), the wordmark rises, and the one
 * fixed line states the whole product: "Verification runs on this device.
 * Nothing leaves it." Fades at ~1900ms, unmounts at ~2450ms. Runs once per
 * session (the WKWebView is a fresh process each launch, so this is once per
 * launch); skippable by click, and reduced-motion collapses the choreography
 * via the global media query.
 */

const SPLASH_KEY = "cachet.splashShown";

export function splashAlreadyShown(): boolean {
  try {
    return sessionStorage.getItem(SPLASH_KEY) === "true";
  } catch {
    return false;
  }
}

export function Splash({ onDone }: { onDone: () => void }) {
  const [leaving, setLeaving] = useState(false);

  useEffect(() => {
    try {
      sessionStorage.setItem(SPLASH_KEY, "true");
    } catch {
      /* storage unavailable: shows again next mount, harmless */
    }
    // Under reduced motion the draw/rise choreography is collapsed by CSS, so
    // holding a static plate for 2.45s would be pure dead time against the
    // 800ms cold-launch budget; show it just long enough to read the line.
    const reduce =
      typeof window.matchMedia === "function" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const fade = setTimeout(() => setLeaving(true), reduce ? 400 : 1900);
    const gone = setTimeout(onDone, reduce ? 700 : 2450);
    return () => {
      clearTimeout(fade);
      clearTimeout(gone);
    };
    // onDone is stable for the splash's lifetime (mounted once per launch).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div
      className={styles.splash}
      data-leaving={leaving ? "true" : undefined}
      onClick={onDone}
      role="presentation"
    >
      <svg viewBox="0 0 240 240" className={styles.splashMark} role="img" aria-label="Cachet mark">
        <g fill="none" stroke="currentColor" strokeLinecap="butt">
          <path
            d="M174.25 86.02 A64 64 0 0 1 80.53 69.56"
            strokeWidth="16"
            pathLength={100}
            className={styles.splashArc1}
          />
          <path
            d="M64.53 88.00 A64 64 0 0 0 174.25 153.98"
            strokeWidth="16"
            pathLength={100}
            className={styles.splashArc2}
          />
        </g>
      </svg>
      <div className={styles.splashWordmark}>Cachet</div>
      <div className={styles.splashLine}>Verification runs on this device. Nothing leaves it.</div>
    </div>
  );
}
