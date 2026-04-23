import { useMemo } from "preact/hooks";

import { Icon, Text } from "@/design-system";

import type { PdfOutlineNode } from "../hooks/usePdfDocument";
import { readerState } from "../state";
import { OutlineNode } from "./OutlineNode";
import styles from "./OutlineRail.module.css";

interface OutlineRailProps {
  outline: PdfOutlineNode[];
}

/**
 * Outline rail — the left-hand navigator.
 *
 * New spec:
 *   open width: 280px
 *   collapsed width: 48px (icon-only)
 *   row height: 32px
 *   label size: --text-body-sm (13/20)
 *   active row: left-edge accent rail (2px) + --state-bg-selected fill
 *   hover row: --state-bg-hover
 *
 * The "active" section is computed from readerState.currentPage: the
 * outline node whose pageNumber is the greatest value <= current page
 * is marked active. This lets the rail track scroll without the reader
 * needing to emit separate outline events.
 */
export function OutlineRail({ outline }: OutlineRailProps) {
  const open = readerState.outlineOpen.value;
  const currentPage = readerState.currentPage.value;
  const activeTitle = useMemo(
    () => findActiveTitle(outline, currentPage),
    [outline, currentPage]
  );

  if (outline.length === 0) {
    // Minimal collapsed chip so the user can see a rail exists but empty.
    // Fully hiding the rail would jog the three-column grid.
    return (
      <aside className={[styles.rail, styles.collapsed].join(" ")} aria-label="Outline (empty)">
        <button
          aria-label="Outline not available for this document"
          className={styles.toggle}
          disabled
          type="button"
        >
          <Icon name="library" size={14} />
        </button>
      </aside>
    );
  }

  return (
    <aside
      aria-label="Document outline"
      className={[styles.rail, !open ? styles.collapsed : ""].filter(Boolean).join(" ")}
    >
      <div className={styles.header}>
        {open ? (
          <Text as="h3" className={styles.headerTitle} tone="tertiary" variant="caption">
            Outline
          </Text>
        ) : null}
        <button
          aria-label={open ? "Collapse outline" : "Expand outline"}
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
            <OutlineNode
              activeTitle={activeTitle}
              key={`${node.title}-${index}`}
              node={node}
            />
          ))}
        </nav>
      ) : null}
    </aside>
  );
}

/**
 * Walk the flat outline (DFS) and find the node whose pageNumber is the
 * largest value <= current page. Returns the node's title (used as a
 * stable-enough identity key for "active" marking inside the tree).
 *
 * Titles collide in badly-structured PDFs, but this is the same
 * identity most reader apps use; we accept the known limitation rather
 * than inventing stable ids the pdfjs outline doesn't give us.
 */
function findActiveTitle(
  outline: PdfOutlineNode[],
  currentPage: number
): string | null {
  let bestTitle: string | null = null;
  let bestPage = -1;
  const visit = (nodes: PdfOutlineNode[]) => {
    for (const n of nodes) {
      if (n.pageNumber != null && n.pageNumber <= currentPage) {
        if (n.pageNumber >= bestPage) {
          bestPage = n.pageNumber;
          bestTitle = n.title;
        }
      }
      if (n.children.length > 0) visit(n.children);
    }
  };
  visit(outline);
  return bestTitle;
}
