import { useState } from "preact/hooks";

import { CachetMark } from "@/design-system";

import styles from "../cachet.module.css";

/**
 * Dev-only harness (cachet.html?demo=mark) for the animated CachetMark.
 * Shows the three motion states (idle / wriggle / reveal) and the currentColor
 * reversal on the dark desk. Not part of the real flow; gated in CachetApp.
 */

const labelStyle = {
  width: "260px",
  fontFamily: "var(--font-serif-body)",
  fontSize: "15px",
  lineHeight: 1.4,
  color: "var(--ink-2)"
};

const rowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "44px",
  minHeight: "150px"
};

export function CachetMarkDemo() {
  const [replay, setReplay] = useState(0);
  return (
    <div className={styles.app} style={{ display: "block", padding: "64px 72px" }}>
      <h1
        style={{
          margin: "0 0 8px",
          fontFamily: "var(--font-serif)",
          fontWeight: 400,
          fontSize: "40px"
        }}
      >
        CachetMark
      </h1>
      <p style={{ margin: "0 0 48px", color: "var(--ink-3)", maxWidth: "58ch" }}>
        The truncated C as an open ring, severed in the upper-left. Ink is currentColor;
        the motion never alters the shape. Honors prefers-reduced-motion.
      </p>

      <div style={rowStyle}>
        <span style={labelStyle}>idle &mdash; the resting breath (rail 26, lectern 76)</span>
        <CachetMark state="idle" size={26} />
        <CachetMark state="idle" size={76} />
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>wriggle &mdash; a small organic tilt</span>
        <CachetMark state="wriggle" size={88} />
      </div>

      <div style={rowStyle}>
        <span style={labelStyle}>reveal &mdash; the ring draws itself (one-shot)</span>
        <CachetMark key={replay} state="reveal" size={120} />
        <button
          type="button"
          onClick={() => setReplay((n) => n + 1)}
          style={{
            font: "inherit",
            color: "var(--ink-1)",
            background: "transparent",
            border: "1px solid var(--hair)",
            borderRadius: "4px",
            padding: "8px 16px",
            cursor: "pointer"
          }}
        >
          Replay reveal
        </button>
      </div>

      <div
        style={{
          ...rowStyle,
          marginTop: "12px",
          background: "var(--ink-1)",
          color: "var(--paper)",
          borderRadius: "8px",
          padding: "20px 44px"
        }}
      >
        <span style={{ ...labelStyle, color: "var(--paper-2)" }}>
          on the dark desk &mdash; reverses via currentColor
        </span>
        <CachetMark state="idle" size={76} />
        <CachetMark key={replay + 1000} state="reveal" size={88} />
      </div>
    </div>
  );
}
