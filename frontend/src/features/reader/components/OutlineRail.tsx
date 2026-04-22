import { Icon, Text } from "@/design-system";

import type { PdfOutlineNode } from "../hooks/usePdfDocument";
import { readerState } from "../state";
import { OutlineNode } from "./OutlineNode";
import styles from "./OutlineRail.module.css";

interface OutlineRailProps {
  outline: PdfOutlineNode[];
}

export function OutlineRail({ outline }: OutlineRailProps) {
  const open = readerState.outlineOpen.value;

  if (outline.length === 0) {
    return null;
  }

  return (
    <aside className={[styles.rail, !open ? styles.collapsed : ""].filter(Boolean).join(" ")}>
      <div className={styles.header}>
        {open ? (
          <Text as="h3" variant="h3" weight="semibold">
            Outline
          </Text>
        ) : null}
        <button
          aria-label={open ? "Hide outline" : "Show outline"}
          className={styles.toggle}
          onClick={() => {
            readerState.outlineOpen.value = !readerState.outlineOpen.value;
          }}
          type="button"
        >
          <Icon name={open ? "chevron-left" : "chevron-right"} size={14} />
        </button>
      </div>
      {open ? (
        <nav className={styles.tree}>
          {outline.map((node, index) => (
            <OutlineNode key={`${node.title}-${index}`} node={node} />
          ))}
        </nav>
      ) : null}
    </aside>
  );
}
