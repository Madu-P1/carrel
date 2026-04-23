import { useState } from "preact/hooks";

import { Icon, Text } from "@/design-system";

import { requestReaderPage } from "../state";
import type { PdfOutlineNode } from "../hooks/usePdfDocument";
import styles from "./OutlineRail.module.css";

interface OutlineNodeProps {
  activeTitle: string | null;
  depth?: number;
  node: PdfOutlineNode;
}

/**
 * One row in the outline tree.
 *
 * Layout: [expand-toggle 20px] [page-link (title + optional page-no)].
 * The page-link is the primary affordance — clicking it jumps the
 * reader to the node's page. The expand-toggle is secondary; it only
 * shows when the node has children.
 *
 * Active state reads through `activeTitle` from the parent. We match by
 * title (the pdfjs outline has no stable id). When a node is active,
 * its row gets a left-edge accent rail via the .rowActive class.
 *
 * Depth 0 defaults to expanded; depth 1+ collapses by default so the
 * rail doesn't explode on chapter-heavy books.
 */
export function OutlineNode({ activeTitle, depth = 0, node }: OutlineNodeProps) {
  const hasChildren = node.children.length > 0;
  const [expanded, setExpanded] = useState(depth < 1);
  const isActive = activeTitle !== null && node.title === activeTitle;

  return (
    <div className={styles.node}>
      <div
        className={[styles.nodeRow, isActive ? styles.rowActive : ""]
          .filter(Boolean)
          .join(" ")}
        style={{ paddingLeft: `${depth * 16}px` }}
      >
        {hasChildren ? (
          <button
            aria-expanded={expanded}
            aria-label={expanded ? "Collapse section" : "Expand section"}
            className={styles.expandBtn}
            onClick={() => setExpanded((value) => !value)}
            type="button"
          >
            <Icon name={expanded ? "chevron-down" : "chevron-right"} size={12} />
          </button>
        ) : (
          <span aria-hidden className={styles.expandBtn} />
        )}
        <button
          className={styles.pageLink}
          onClick={() => {
            if (node.pageNumber != null) {
              requestReaderPage(node.pageNumber);
            }
          }}
          title={node.title}
          type="button"
        >
          <span className={styles.nodeTitle}>{node.title}</span>
          {node.pageNumber != null ? (
            <Text className={styles.pageMeta} tone="tertiary" variant="caption">
              {node.pageNumber}
            </Text>
          ) : null}
        </button>
      </div>
      {hasChildren && expanded ? (
        <div className={styles.children}>
          {node.children.map((child, index) => (
            <OutlineNode
              activeTitle={activeTitle}
              depth={depth + 1}
              key={`${child.title}-${index}`}
              node={child}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
