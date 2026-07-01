/**
 * The PDF pane of the Document Examination overlay: one page of the original
 * record, rendered with pdf.js (canvas + selectable text layer), with the
 * cited passage anchored in place.
 *
 * Anchoring is honest end to end: the passage is located by exact normalized
 * match (anchor.ts) starting from the cited page and spiralling outward; a
 * found passage gets an ink underline and a quiet pill, a missing one gets a
 * visible note, never a guessed highlight. The worker, fonts, and bytes are
 * all local (pdfjs-setup + the loopback file route); nothing leaves the
 * machine.
 */
import { useEffect, useRef, useState } from "preact/hooks";

import type { PDFDocumentProxy, RenderTask, TextItem } from "pdfjs-dist/types/src/display/api";

import { Spinner } from "@/design-system";
import { loadPdfJs } from "@/features/reader/lib/pdfjs-setup";
import verifyStyles from "@/features/verify/VerifyView.module.css";

import {
  findAnchorPage,
  matchQuoteInItems,
  spansToViewportRects,
  type AnchorRect,
  type PdfTextItemLike
} from "./anchor";
import { authHeaders, documentFileUrl } from "./fetchDocumentFile";
import styles from "./examine.module.css";

interface PdfExaminationProps {
  docId: string;
  page?: number | null;
  quote?: string | null;
  /** Reports a load failure to the parent, which owns the named-cause
   *  failure panel and Retry control (DocumentExamination.tsx). */
  onError?: (message: string) => void;
}

type AnchorState =
  | { kind: "none" }
  | { kind: "searching" }
  | { kind: "found"; page: number }
  | { kind: "absent" };

function clampPage(page: number, pageCount: number): number {
  return Math.max(1, Math.min(pageCount, page));
}

/**
 * The page step for a keydown over the PDF pane, or 0 when the key must be left
 * to the browser. Only a BARE Left/Right arrow pages: a modifier (Shift to
 * extend a selection, Cmd/Ctrl/Alt for shortcuts) or a keypress whose target is
 * inside the selectable text layer is left alone, so a reader selecting text in
 * the record moves the caret instead of flipping the page. Exported pure for
 * direct unit testing (PdfExamination.test.tsx).
 */
export function arrowPageDelta(event: KeyboardEvent, textLayer: Node | null): -1 | 0 | 1 {
  if (
    event.defaultPrevented ||
    event.shiftKey ||
    event.metaKey ||
    event.ctrlKey ||
    event.altKey
  ) {
    return 0;
  }
  const target = event.target as Node | null;
  if (target && textLayer?.contains(target)) {
    return 0;
  }
  if (event.key === "ArrowLeft") {
    return -1;
  }
  if (event.key === "ArrowRight") {
    return 1;
  }
  return 0;
}

async function pageTextItems(pdf: PDFDocumentProxy, pageNumber: number): Promise<PdfTextItemLike[]> {
  const page = await pdf.getPage(pageNumber);
  const content = await page.getTextContent();
  return content.items.filter((item): item is TextItem => "str" in item);
}

export function PdfExamination({ docId, page, quote, onError }: PdfExaminationProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [pdf, setPdf] = useState<PDFDocumentProxy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pageCount, setPageCount] = useState(0);
  const [currentPage, setCurrentPage] = useState(Math.max(1, page ?? 1));
  const [anchor, setAnchor] = useState<AnchorState>({ kind: quote ? "searching" : "none" });
  const [anchorRects, setAnchorRects] = useState<AnchorRect[]>([]);
  const [containerWidth, setContainerWidth] = useState(0);
  const [pageRendered, setPageRendered] = useState(false);

  // Load the document once per record.
  useEffect(() => {
    let disposed = false;
    let task: { destroy(): Promise<unknown> } | null = null;
    let loaded: PDFDocumentProxy | null = null;
    setPdf(null);
    setError(null);
    setPageCount(0);

    void (async () => {
      try {
        const pdfjsLib = await loadPdfJs();
        const headers = await authHeaders();
        const loadingTask = pdfjsLib.getDocument({
          disableAutoFetch: true,
          disableStream: false,
          httpHeaders: headers,
          url: documentFileUrl(docId)
        });
        task = loadingTask;
        const doc = await loadingTask.promise;
        loaded = doc;
        if (disposed) {
          void doc.destroy();
          return;
        }
        setPdf(doc);
        setPageCount(doc.numPages);
        setCurrentPage((current) => clampPage(page ?? current, doc.numPages));
      } catch (cause) {
        if (!disposed) {
          const message =
            cause instanceof Error && cause.message
              ? cause.message
              : "The record could not be opened.";
          setError(message);
          onError?.(message);
        }
      }
    })();

    return () => {
      disposed = true;
      if (loaded) {
        void loaded.destroy();
      } else if (task) {
        void task.destroy();
      }
    };
  }, [docId, page, onError]);

  // Locate the cited passage, preferring the cited page.
  useEffect(() => {
    if (!pdf || !quote) {
      setAnchor(quote ? { kind: "searching" } : { kind: "none" });
      return;
    }
    let disposed = false;
    setAnchor({ kind: "searching" });
    void findAnchorPage((n) => pageTextItems(pdf, n), pdf.numPages, quote, page).then(
      (found) => {
        if (disposed) {
          return;
        }
        if (found) {
          setAnchor({ kind: "found", page: found.page });
          setCurrentPage(found.page);
        } else {
          setAnchor({ kind: "absent" });
        }
      },
      () => {
        if (!disposed) {
          setAnchor({ kind: "absent" });
        }
      }
    );
    return () => {
      disposed = true;
    };
  }, [pdf, quote, page]);

  // Track the pane width so the page renders fit-to-width.
  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }
    const update = () => setContainerWidth(container.clientWidth);
    update();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", update);
      return () => window.removeEventListener("resize", update);
    }
    const observer = new ResizeObserver(update);
    observer.observe(container);
    return () => observer.disconnect();
  }, [pdf]);

  // Render the current page: canvas, text layer, then the anchor overlay.
  useEffect(() => {
    if (!pdf) {
      return;
    }
    let cancelled = false;
    let renderTask: RenderTask | null = null;
    setPageRendered(false);
    setAnchorRects([]);

    void (async () => {
      const pdfjsLib = await loadPdfJs();
      const pdfPage = await pdf.getPage(currentPage);
      const baseViewport = pdfPage.getViewport({ scale: 1 });
      const available = containerWidth > 0 ? containerWidth - 48 : baseViewport.width;
      const scale = Math.max(0.4, Math.min(2.4, available / baseViewport.width));
      const viewport = pdfPage.getViewport({ scale });

      const canvas = canvasRef.current;
      const textLayerHost = textLayerRef.current;
      if (cancelled || !canvas || !textLayerHost) {
        return;
      }
      const context = canvas.getContext("2d");
      if (!context) {
        return;
      }
      const outputScale = window.devicePixelRatio || 1;
      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      context.setTransform(outputScale, 0, 0, outputScale, 0, 0);

      textLayerHost.innerHTML = "";
      textLayerHost.style.setProperty("--scale-factor", String(viewport.scale));
      textLayerHost.style.width = `${viewport.width}px`;
      textLayerHost.style.height = `${viewport.height}px`;

      renderTask = pdfPage.render({ canvasContext: context, viewport });
      try {
        await renderTask.promise;
      } catch (cause) {
        // O6: a real (non-cancellation) render failure must surface as the
        // named failure panel, not throw out of this async IIFE and leave a
        // perpetual "Rendering page N" spinner. A cancellation is a normal
        // re-render/unmount and is silently ignored.
        const name = (cause as { name?: string } | null)?.name;
        if (name !== "RenderingCancelledException" && !cancelled) {
          onError?.("The record's page could not be rendered.");
        }
        return;
      } finally {
        renderTask = null;
      }
      if (cancelled || !textLayerRef.current) {
        return;
      }

      try {
        const content = await pdfPage.getTextContent();
        const textLayer = new pdfjsLib.TextLayer({
          container: textLayerRef.current,
          textContentSource: content,
          viewport
        });
        await textLayer.render();
        if (cancelled) {
          return;
        }
        setPageRendered(true);

        if (quote) {
          const items = content.items.filter((entry): entry is TextItem => "str" in entry);
          const match = matchQuoteInItems(quote, items);
          setAnchorRects(match ? spansToViewportRects(match.spans, items, viewport) : []);
        }
      } catch {
        // O6: text-content / text-layer extraction can also fail; surface it as
        // the named failure panel rather than an uncaught rejection that leaves
        // the "Rendering page N" spinner up forever.
        if (!cancelled) {
          onError?.("The record's page could not be rendered.");
        }
      }
    })();

    return () => {
      cancelled = true;
      renderTask?.cancel();
    };
  }, [pdf, currentPage, containerWidth, quote, onError]);

  // ← / → page through the record while the overlay is open, but only a bare
  // arrow over the page chrome pages: arrowPageDelta leaves Shift+Arrow and any
  // arrow inside the selectable text layer to the browser so selection is never
  // hijacked.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const delta = arrowPageDelta(event, textLayerRef.current);
      if (delta !== 0) {
        setCurrentPage((current) => clampPage(current + delta, pageCount || 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pageCount]);

  // A new page starts at its top; carrying the previous page's scroll
  // position lands the reader mid-page for no reason.
  useEffect(() => {
    containerRef.current?.scrollTo({ behavior: "auto", top: 0 });
  }, [currentPage]);

  if (error) {
    // The named-cause failure panel + Retry control render one level up, in
    // DocumentExamination.tsx, once onError has reported this message.
    return null;
  }

  if (!pdf) {
    return (
      <div className={styles.paneMessage}>
        <Spinner size={16} />
        <span>Opening the record…</span>
      </div>
    );
  }

  // The pill is a margin tab: its RIGHT edge sits just left of the underlined
  // run, in the page's own gutter, aligned to the first underlined line. A
  // pill wider than the gutter overhangs the page's left edge like a physical
  // exhibit tab; it can never cover a glyph.
  const firstRect = anchorRects[0];
  const pillStyle = firstRect
    ? {
        right: `calc(100% - ${Math.max(firstRect.left - 8, 0)}px)`,
        top: `${Math.max(2, firstRect.top - 2)}px`
      }
    : undefined;
  const showAnchorHere = anchor.kind === "found" && anchor.page === currentPage;

  return (
    <div className={styles.pdfPane}>
      <div className={styles.pdfToolbar}>
        {/* A one-page record needs no pager; two disabled buttons are noise. */}
        {pageCount > 1 ? (
          <div className={styles.pageControls}>
            <button
              type="button"
              className={styles.pageButton}
              disabled={currentPage <= 1}
              onClick={() => setCurrentPage((current) => Math.max(1, current - 1))}
            >
              Previous
            </button>
            <span className={styles.pageIndicator}>
              Page {currentPage} of {pageCount}
            </span>
            <button
              type="button"
              className={styles.pageButton}
              disabled={currentPage >= pageCount}
              onClick={() => setCurrentPage((current) => clampPage(current + 1, pageCount))}
            >
              Next
            </button>
          </div>
        ) : (
          <span className={styles.pageIndicator}>One page</span>
        )}
        <span className={styles.anchorStatus} role="status">
          {anchor.kind === "searching" ? (
            <span className={styles.anchorNote}>Locating the cited passage…</span>
          ) : anchor.kind === "absent" ? (
            <span className={styles.anchorNoteAbsent}>
              Could not locate the cited passage in this record.
            </span>
          ) : anchor.kind === "found" && anchor.page !== currentPage ? (
            <button
              type="button"
              className={styles.anchorReturn}
              onClick={() => setCurrentPage(anchor.page)}
            >
              Return to the cited passage on p. {anchor.page}
            </button>
          ) : anchor.kind === "found" ? (
            <span className={styles.anchorNote}>Cited passage anchored on this page.</span>
          ) : null}
        </span>
      </div>
      <div className={styles.pdfScroll} ref={containerRef}>
        <div className={styles.pdfPageBox}>
          <canvas ref={canvasRef} />
          <div className={`${styles.pdfTextLayer} textLayer`} ref={textLayerRef} />
          {showAnchorHere
            ? anchorRects.map((rect, index) => (
                <div
                  key={`${currentPage}-${index}`}
                  className={styles.anchorRect}
                  style={{
                    height: `${rect.height}px`,
                    left: `${rect.left}px`,
                    top: `${rect.top}px`,
                    width: `${rect.width}px`
                  }}
                />
              ))
            : null}
          {showAnchorHere && pillStyle ? (
            <span
              className={`${verifyStyles.verdictBadge} ${verifyStyles.badgePass} ${styles.anchorPill}`}
              style={pillStyle}
            >
              Cited passage
            </span>
          ) : null}
          {!pageRendered ? (
            <div className={styles.pageLoading}>
              <Spinner size={16} label={`Rendering page ${currentPage}`} />
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
