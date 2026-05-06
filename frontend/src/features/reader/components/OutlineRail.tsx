import type { JSX } from "preact";
import { useMemo } from "preact/hooks";

import { Icon, Text } from "@/design-system";

import type { PdfOutlineNode } from "../hooks/usePdfDocument";
import { readerState, READER_OUTLINE_WIDTH, setReaderOutlineWidth } from "../state";

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
  const focusMode = readerState.focusMode.value;
  const open = readerState.outlineOpen.value;
  const currentPage = readerState.currentPage.value;
  const outlineWidth = readerState.outlineWidth.value;
  const activeTitle = useMemo(
    () => findActiveTitle(outline, currentPage),
    [outline, currentPage]
  );

  if (focusMode) {
    return null;
  }

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

  const startResize = (event: JSX.TargetedPointerEvent<HTMLDivElement>) => {
    if (event.button !== 0) return;
    event.preventDefault();

    const startX = event.clientX;
    const startWidth = readerState.outlineWidth.value;
    const previousCursor = document.body.style.cursor;
    const previousUserSelect = document.body.style.userSelect;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    const onPointerMove = (moveEvent: PointerEvent) => {
      setReaderOutlineWidth(startWidth + moveEvent.clientX - startX);
    };
    const stopResize = () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", stopResize);
      window.removeEventListener("pointercancel", stopResize);
      document.body.style.cursor = previousCursor;
      document.body.style.userSelect = previousUserSelect;
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", stopResize);
    window.addEventListener("pointercancel", stopResize);
  };

  const resizeFromKeyboard = (event: JSX.TargetedKeyboardEvent<HTMLDivElement>) => {
    const step = event.shiftKey ? 32 : 16;
    let nextWidth: number | null = null;
    switch (event.key) {
      case "ArrowLeft":
        nextWidth = outlineWidth - step;
        break;
      case "ArrowRight":
        nextWidth = outlineWidth + step;
        break;
      case "Home":
        nextWidth = READER_OUTLINE_WIDTH.min;
        break;
      case "End":
        nextWidth = READER_OUTLINE_WIDTH.max;
        break;
      default:
        return;
    }
    event.preventDefault();
    setReaderOutlineWidth(nextWidth);
  };

  return (
    <aside
      aria-label="Document outline"
      className={[styles.rail, !open ? styles.collapsed : ""].filter(Boolean).join(" ")}
      style={{ "--outline-rail-width": `${outlineWidth}px` } as JSX.CSSProperties}
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
      {/*
        Resize separator. role="separator" is structurally non-interactive
        in lint's eyes, but this one IS interactive (keyboard via onKeyDown,
        pointer via onPointerDown). Same pattern as the AppShell resize
        handles. tabIndex toggles between 0 (when open) and -1.
      */}
      {/* eslint-disable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
      <div
        aria-hidden={!open}
        aria-label="Resize document outline"
        aria-orientation="vertical"
        aria-valuemax={READER_OUTLINE_WIDTH.max}
        aria-valuemin={READER_OUTLINE_WIDTH.min}
        aria-valuenow={outlineWidth}
        className={[styles.resizeHandle, !open ? styles.resizeHandleHidden : ""]
          .filter(Boolean)
          .join(" ")}
        data-testid="outline-resize-handle"
        onKeyDown={resizeFromKeyboard}
        onPointerDown={startResize}
        role="separator"
        tabIndex={open ? 0 : -1}
      />
      {/* eslint-enable jsx-a11y/no-noninteractive-element-interactions, jsx-a11y/no-noninteractive-tabindex */}
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
