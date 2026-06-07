import { useState } from "preact/hooks";

import { useFlipReorder } from "@/features/verify/useFlipReorder";

/**
 * Dev-only harness (cachet.html?demo=stream) for SM-V2 The Read.
 *
 * The streaming verdict list only re-sorts during a live verify, which needs the
 * backend. This drives the same generic FLIP hook (useFlipReorder) with simple
 * cards so the reorder animation can be verified deterministically: "Resolve a
 * flag" moves the last card to the top (a flag rising as its check lands) and
 * the hook animates the position change. Not shipped in the real flow.
 */
const INITIAL = [
  { key: "a", label: "Statement 1" },
  { key: "b", label: "Statement 2" },
  { key: "c", label: "Statement 3" },
  { key: "d", label: "Statement 4 (flag)" }
];

const card = {
  padding: "14px 16px",
  border: "1px solid rgba(28,24,20,.14)",
  borderRadius: "3px",
  background: "#fcfaf4",
  fontFamily: "Charter, Georgia, serif",
  color: "#1c1814"
};

export function StreamFlipDemo() {
  const [order, setOrder] = useState(INITIAL);
  const listRef = useFlipReorder<HTMLDivElement>();

  function riseLast() {
    setOrder((current) => {
      if (current.length < 2) return current;
      const next = [...current];
      const last = next.pop()!;
      return [last, ...next];
    });
  }

  return (
    <div style={{ maxWidth: "60ch", margin: "48px auto", padding: "0 24px" }}>
      <button
        id="flip-rise"
        type="button"
        onClick={riseLast}
        style={{ marginBottom: "16px", padding: "8px 16px" }}
      >
        Resolve a flag (rise)
      </button>
      <div ref={listRef} style={{ display: "flex", flexDirection: "column", gap: "12px" }}>
        {order.map((c) => (
          <div key={c.key} data-flip-key={c.key} style={card}>
            {c.label}
          </div>
        ))}
      </div>
    </div>
  );
}
