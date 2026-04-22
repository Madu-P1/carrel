import { useState } from "preact/hooks";
import type { ComponentChildren } from "preact";

import { Icon } from "../Icon";
import styles from "./Pane.module.css";

export interface PaneProps {
  title: string;
  defaultCollapsed?: boolean;
  collapsible?: boolean;
  children?: ComponentChildren;
}

export function Pane({
  title,
  defaultCollapsed = false,
  collapsible = true,
  children
}: PaneProps) {
  const [collapsed, setCollapsed] = useState(defaultCollapsed);

  return (
    <section
      className={[styles.pane, collapsed ? styles.collapsed : ""]
        .filter(Boolean)
        .join(" ")}
    >
      <header className={styles.header}>
        <span className={styles.title}>{title}</span>
        {collapsible ? (
          <button
            aria-expanded={!collapsed}
            className={styles.toggle}
            onClick={() => setCollapsed((value) => !value)}
            type="button"
          >
            <Icon name={collapsed ? "chevron-down" : "chevron-up"} />
          </button>
        ) : null}
      </header>
      <div className={styles.body}>{children}</div>
    </section>
  );
}
