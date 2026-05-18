import { useEffect, useState } from "preact/hooks";
import type { MutableRef } from "preact/hooks";

import { Button, Icon, Tooltip } from "@/design-system";
import { events } from "@/services/metrics/events";

import {
  readerState,
  requestReaderPage,
  setReaderFitMode,
  setReaderFocusMode,
  setReaderScale,
  zoomReaderBy
} from "../state";
import styles from "./PdfToolbar.module.css";

interface PdfToolbarProps {
  filename: string;
  fileType: string;
  leftPanelOpen: boolean;
  outlineOpen: boolean;
  pageCount: number;
  onCreateCard: () => void;
  onOpenSearch: () => void;
  onToggleAppSidebar: () => void;
  onToggleOutline: () => void;
  onToggleSourcePanel: () => void;
  rightPanelOpen: boolean;
  /** Ref attached to the toolbar root so SM-1 (library card flight) can
   *  morph from the clicked card into this bar. Previously attached to a
   *  separate page header; moved here so the reader gains vertical space
   *  for the document canvas. */
  flightRef?: MutableRef<HTMLDivElement | null>;
}

/**
 * PDF toolbar — three-zone layout.
 *
 * Zone layout:
 *   LEFT    file title + file-type chip (SM-1 flight target)
 *   CENTER  page controls (prev / page input / next / fit / zoom)
 *   RIGHT   actions (search, overflow)
 *
 * Height is fixed at 44px so the toolbar reads as architecture, not
 * content. All controls snap to --control-height-sm/md and
 * --radius-button so a button, a field, and a chip on the same row share
 * rhythm. No one-off paddings survive this file.
 *
 * The page input is a native <input type="number"> by convention — the
 * Input primitive is overkill for one-field numeric entry, and tests
 * select it by role=spinbutton which pdfjs users know from every other
 * reader.
 */
export function PdfToolbar({
  filename,
  fileType,
  leftPanelOpen,
  outlineOpen,
  pageCount,
  onCreateCard,
  onOpenSearch,
  onToggleAppSidebar,
  onToggleOutline,
  onToggleSourcePanel,
  rightPanelOpen,
  flightRef,
}: PdfToolbarProps) {
  const currentPage = readerState.currentPage.value;
  const fitMode = readerState.fitMode.value;
  const focusMode = readerState.focusMode.value;
  const scale = readerState.scale.value;
  const [pageInput, setPageInput] = useState(String(currentPage));

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  const commitPage = () => {
    const parsed = Number.parseInt(pageInput, 10);
    if (Number.isNaN(parsed)) {
      setPageInput(String(currentPage));
      return;
    }
    requestReaderPage(parsed);
  };

  const ft = (fileType || "FILE").toUpperCase();
  const toggleFocusMode = () => {
    const enabled = !focusMode;
    setReaderFocusMode(enabled);
    void events.track("reader.focus_toggled", { enabled }, "reader");
  };

  return (
    <div className={[styles.toolbar, focusMode ? styles.toolbarFocus : ""].filter(Boolean).join(" ")} ref={flightRef}>
      {/* --- LEFT ZONE: title + file-type chip ------------------------ */}
      <div className={styles.zoneLeft}>
        <span aria-label={`File type: ${ft}`} className={styles.fileChip}>
          {ft}
        </span>
        <h1 className={styles.title} title={filename}>
          {filename}
        </h1>
      </div>

      {/* --- CENTER ZONE: page controls ------------------------------- */}
      <div className={styles.zoneCenter}>
        <Tooltip content="Previous page">
          <button
            aria-label="Previous page"
            className={styles.iconBtn}
            disabled={currentPage <= 1}
            onClick={() => requestReaderPage(currentPage - 1)}
            type="button"
          >
            <Icon name="chevron-left" size={14} />
          </button>
        </Tooltip>
        <div className={styles.pageField}>
          <input
            aria-label="Page number"
            className={styles.pageInput}
            max={Math.max(pageCount, 1)}
            min={1}
            onBlur={commitPage}
            onChange={(event) => setPageInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") commitPage();
            }}
            type="number"
            value={pageInput}
          />
          <span className={styles.pageSep}>/</span>
          <span className={styles.pageTotal}>{pageCount || 0}</span>
        </div>
        <Tooltip content="Next page">
          <button
            aria-label="Next page"
            className={styles.iconBtn}
            disabled={pageCount === 0 || currentPage >= pageCount}
            onClick={() => requestReaderPage(currentPage + 1)}
            type="button"
          >
            <Icon name="chevron-right" size={14} />
          </button>
        </Tooltip>

        <div className={styles.divider} aria-hidden />

        <Tooltip content="Fit width">
          <button
            aria-label="Fit width"
            aria-pressed={fitMode === "fit-width"}
            className={[
              styles.iconBtn,
              fitMode === "fit-width" ? styles.iconBtnActive : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => setReaderFitMode("fit-width")}
            type="button"
          >
            <span className={styles.fitGlyph}>W</span>
          </button>
        </Tooltip>
        <Tooltip content="Fit page">
          <button
            aria-label="Fit page"
            aria-pressed={fitMode === "fit-page"}
            className={[
              styles.iconBtn,
              fitMode === "fit-page" ? styles.iconBtnActive : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={() => setReaderFitMode("fit-page")}
            type="button"
          >
            <span className={styles.fitGlyph}>P</span>
          </button>
        </Tooltip>
        <Tooltip content="Zoom out">
          <button
            aria-label="Zoom out"
            className={styles.iconBtn}
            onClick={() => zoomReaderBy(-0.1)}
            type="button"
          >
            <span className={styles.zoomGlyph}>−</span>
          </button>
        </Tooltip>
        <Tooltip content="Reset zoom to 100%">
          <button
            aria-label="Reset zoom to 100%"
            className={styles.zoomBtn}
            onClick={() => setReaderScale(1)}
            type="button"
          >
            {Math.round(scale * 100)}%
          </button>
        </Tooltip>
        <Tooltip content="Zoom in">
          <button
            aria-label="Zoom in"
            className={styles.iconBtn}
            onClick={() => zoomReaderBy(0.1)}
            type="button"
          >
            <span className={styles.zoomGlyph}>+</span>
          </button>
        </Tooltip>
      </div>

      {/* --- RIGHT ZONE: actions -------------------------------------- */}
      <div className={styles.zoneRight}>
        <div className={styles.panelGroup} aria-label="Reader panels" role="group">
          <Tooltip content={leftPanelOpen ? "Hide app sidebar" : "Show app sidebar"}>
            <button
              aria-label={leftPanelOpen ? "Hide app sidebar" : "Show app sidebar"}
              aria-pressed={leftPanelOpen}
              className={[
                styles.iconBtn,
                leftPanelOpen ? styles.iconBtnActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={onToggleAppSidebar}
              type="button"
            >
              <Icon name="dashboard" size={14} />
            </button>
          </Tooltip>
          <Tooltip content={outlineOpen ? "Hide document outline" : "Show document outline"}>
            <button
              aria-label={outlineOpen ? "Hide document outline" : "Show document outline"}
              aria-pressed={outlineOpen}
              className={[
                styles.iconBtn,
                outlineOpen ? styles.iconBtnActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={onToggleOutline}
              type="button"
            >
              <Icon name="library" size={14} />
            </button>
          </Tooltip>
          <Tooltip content={rightPanelOpen ? "Hide source panel" : "Show source panel"}>
            <button
              aria-label={rightPanelOpen ? "Hide source panel" : "Show source panel"}
              aria-pressed={rightPanelOpen}
              className={[
                styles.iconBtn,
                rightPanelOpen ? styles.iconBtnActive : "",
              ]
                .filter(Boolean)
                .join(" ")}
              onClick={onToggleSourcePanel}
              type="button"
            >
              <Icon name="doc" size={14} />
            </button>
          </Tooltip>
        </div>
        <div className={styles.divider} aria-hidden />
        <Tooltip content={focusMode ? "Exit focus mode" : "Enter focus mode"}>
          <button
            aria-label={focusMode ? "Exit focus mode" : "Enter focus mode"}
            aria-pressed={focusMode}
            className={[
              styles.iconBtn,
              focusMode ? styles.iconBtnActive : "",
            ]
              .filter(Boolean)
              .join(" ")}
            onClick={toggleFocusMode}
            type="button"
          >
            <Icon name="focus" size={14} />
          </button>
        </Tooltip>
        <Button
          onClick={onCreateCard}
          size="sm"
          variant="secondary"
        >
          New card
        </Button>
        <Button
          keyHint="⌘F"
          leadingIcon={<Icon name="search" size={14} />}
          onClick={onOpenSearch}
          size="sm"
          variant="secondary"
        >
          Find
        </Button>
      </div>
    </div>
  );
}
