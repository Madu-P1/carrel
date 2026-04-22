import { useState } from "preact/hooks";

import { Badge, Icon, Text } from "@/design-system";

import styles from "../AskView.module.css";

interface UnsupportedSpansProps {
  claimCount?: number;
  items: string[];
}

export function UnsupportedSpans({ claimCount = 0, items }: UnsupportedSpansProps) {
  const [open, setOpen] = useState(false);

  if (items.length === 0) {
    return null;
  }

  const revealDelay = 80 + claimCount * 60 + 240;

  return (
    <section
      className={[styles.unsupportedWrap, "anim-fadeUp"].join(" ")}
      style={{ animationDelay: `${revealDelay}ms` }}
    >
      <button
        aria-expanded={open}
        className={[styles.unsupportedHeader, open ? styles.unsupportedOpen : ""]
          .filter(Boolean)
          .join(" ")}
        onClick={() => setOpen((value) => !value)}
        type="button"
      >
        <Badge tone="warning">Not in your sources</Badge>
        <Icon name={open ? "chevron-up" : "chevron-down"} />
      </button>
      {open ? (
        <div className={styles.unsupportedBody}>
          <ul className={styles.unsupportedList}>
            {items.map((item) => (
              <li key={item}>
                <Text>{item}</Text>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}
