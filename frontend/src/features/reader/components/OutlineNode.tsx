import { useState } from "preact/hooks";

import { Icon, Text } from "@/design-system";

import { requestReaderPage } from "../state";
import type { PdfOutlineNode } from "../hooks/usePdfDocument";
import styles from "./OutlineRail.module.css";

interface OutlineNodeProps {
  depth?: number;
  node: PdfOutlineNode;
}

export function OutlineNode({ depth = 0, node }: OutlineNodeProps) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(depth < 1);

  return (
    <div className={styles.node}>
      <div className={styles.nodeRow}>
        {hasChildren ? (
          <button
            aria-label={expanded ? "Collapse outline section" : "Expand outline section"}
            className={styles.nodeButton}
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            <Icon name={expanded ? "chevron-down" : "chevron-right"} size={14} />
          </button>
        ) : (
          <span className={styles.nodeButton} />
        )}
        <button
          className={styles.pageLink}
          onClick={() => {
            if (node.pageNumber != null) {
              requestReaderPage(node.pageNumber);
            }
          }}
          type="button"
        >
          <Text className={styles.nodeTitle}>{node.title}</Text>
          {node.pageNumber != null ? (
            <Text className={styles.pageMeta} tone="tertiary" variant="caption">
              p. {node.pageNumber}
            </Text>
          ) : null}
        </button>
      </div>
      {hasChildren && expanded ? (
        <div className={styles.children}>
          {node.children.map((child, index) => (
            <OutlineNode depth={depth + 1} key={`${child.title}-${index}`} node={child} />
          ))}
        </div>
      ) : null}
    </div>
  );
}
