import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";


import { Button, Card, Text, toast } from "@/design-system";
import { anchors } from "@/services/api/endpoints";

import { usePageVirtualizer } from "../hooks/usePageVirtualizer";
import type { PdfState } from "../hooks/usePdfDocument";
import { useReaderSelection } from "../hooks/useReaderSelection";
import styles from "../ReaderView.module.css";
import {
  persistReaderRestorationState,
  readerState,
  readReaderRestorationState,
  setReaderCurrentPage
} from "../state";

import { PdfPage } from "./PdfPage";
import { ReaderErrorState } from "./ReaderErrorState";
import { ReaderLoadingState } from "./ReaderLoadingState";

interface PdfViewerProps {
  docId: string;
  pdfState: PdfState;
}

async function firstPageSize(pdf: PDFDocumentProxy, scale: number) {
  const page = await pdf.getPage(1);
  const viewport = page.getViewport({ scale });
  return {
    height: viewport.height,
    width: viewport.width
  };
}

export function PdfViewer({ docId, pdfState }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const restoreAppliedRef = useRef<string | null>(null);
  const lastPersistedAtRef = useRef(0);
  const { doc, error, loading, pageCount } = pdfState;
  const fitMode = readerState.fitMode.value;
  const focusMode = readerState.focusMode.value;
  const requestedPage = readerState.requestedPage.value;
  const scale = readerState.scale.value;
  const selectedText = readerState.selectedText.value;
  const [baseHeight, setBaseHeight] = useState(960);
  const [baseWidth, setBaseWidth] = useState(720);
  const [containerWidth, setContainerWidth] = useState(960);
  const [containerHeight, setContainerHeight] = useState(720);

  useReaderSelection(containerRef);

  useEffect(() => {
    const container = containerRef.current;
    if (!container) {
      return;
    }

    const updateBounds = () => {
      setContainerWidth(container.clientWidth);
      setContainerHeight(container.clientHeight);
    };

    updateBounds();
    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => updateBounds());
      observer.observe(container);
    } else {
      window.addEventListener("resize", updateBounds);
    }

    return () => {
      if (observer) {
        observer.disconnect();
      } else {
        window.removeEventListener("resize", updateBounds);
      }
    };
  }, []);

  useEffect(() => {
    if (!doc.value) {
      return;
    }

    let cancelled = false;
    void firstPageSize(doc.value, 1).then((size) => {
      if (!cancelled) {
        setBaseHeight(size.height);
        setBaseWidth(size.width);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [doc.value]);

  const effectiveScale = useMemo(() => {
    const horizontalChrome = focusMode ? 96 : 48;
    const verticalChrome = focusMode ? 96 : 48;
    const availableWidth = Math.max(1, (focusMode ? Math.min(containerWidth, 1180) : containerWidth) - horizontalChrome);
    const availableHeight = Math.max(1, (focusMode ? Math.min(containerHeight, 1400) : containerHeight) - verticalChrome);

    if (fitMode === "fit-width") {
      return Math.max(0.4, availableWidth / Math.max(baseWidth, 1));
    }
    if (fitMode === "fit-page") {
      return Math.max(
        0.4,
        Math.min(availableWidth / Math.max(baseWidth, 1), availableHeight / Math.max(baseHeight, 1))
      );
    }
    return scale;
  }, [baseHeight, baseWidth, containerHeight, containerWidth, fitMode, focusMode, scale]);

  const pageGap = focusMode ? 48 : 32;
  const railChrome = focusMode ? 96 : 48;
  const estimatedPageHeight = Math.max(320, baseHeight * effectiveScale + pageGap);
  const estimatedPageWidth = Math.max(240, baseWidth * effectiveScale);
  const railWidth = Math.max(containerWidth, estimatedPageWidth + railChrome);
  const persistScrollState = useCallback((state: { currentPage: number; scrollTop: number }) => {
    const now = Date.now();
    if (now - lastPersistedAtRef.current < 350) {
      return;
    }
    lastPersistedAtRef.current = now;
    persistReaderRestorationState(docId, {
      page: state.currentPage,
      scrollTop: state.scrollTop
    });
  }, [docId]);
  const { totalHeight, visiblePages } = usePageVirtualizer({
    containerRef,
    onScrollStateChange: persistScrollState,
    pageCount: pageCount.value,
    pageHeight: estimatedPageHeight
  });
  const visibleSet = useMemo(() => new Set(visiblePages), [visiblePages]);

  useEffect(() => {
    restoreAppliedRef.current = null;
    lastPersistedAtRef.current = 0;
  }, [docId]);

  useEffect(() => {
    if (restoreAppliedRef.current !== docId) {
      return;
    }
    persistReaderRestorationState(docId, {
      fitMode,
      scale
    });
  }, [docId, fitMode, scale]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || !doc.value || pageCount.value <= 0 || restoreAppliedRef.current === docId) {
      return;
    }

    const restored = readReaderRestorationState(docId);
    restoreAppliedRef.current = docId;
    if (!restored) {
      return;
    }

    window.requestAnimationFrame(() => {
      const top = restored.scrollTop > 0
        ? restored.scrollTop
        : estimatedPageHeight * (restored.page - 1);
      container.scrollTo({
        behavior: "auto",
        top
      });
      setReaderCurrentPage(restored.page);
    });
  }, [doc.value, docId, estimatedPageHeight, pageCount.value]);

  useEffect(() => {
    if (!containerRef.current || requestedPage === null) {
      return;
    }

    containerRef.current.scrollTo({
      behavior: "smooth",
      top: estimatedPageHeight * (requestedPage - 1)
    });
    readerState.requestedPage.value = null;
  }, [estimatedPageHeight, requestedPage]);

  useEffect(() => {
    const container = containerRef.current;
    return () => {
      if (!container) return;
      persistReaderRestorationState(docId, {
        page: readerState.currentPage.value,
        scrollTop: container.scrollTop
      });
    };
  }, [docId]);

  if (loading.value && !doc.value) {
    return <ReaderLoadingState />;
  }

  if (error.value) {
    return <ReaderErrorState error={error.value} />;
  }

  if (!doc.value) {
    return null;
  }

  const pdf = doc.value;

  return (
    <div className={styles.viewerShell}>
      {selectedText ? (
        <Card className={styles.selectionBanner} padding="sm">
          <Text tone="secondary">
            Selection captured: "{selectedText.slice(0, 140)}
            {selectedText.length > 140 ? "..." : ""}"
          </Text>
          <Button
            size="sm"
            variant="secondary"
            onClick={() => {
              void anchors.create({
                document_id: docId,
                quote_text: selectedText,
                origin: "highlight",
                page_num: readerState.currentPage.value || null,
                confidence: 0.7
              })
                .then(() => {
                  readerState.selectedText.value = "";
                  toast.success("Anchor saved", "The highlight is now available in the Anchor Column.");
                })
                .catch(() => toast.error("Save failed", "Carrel could not save this highlight."));
            }}
          >
            Save anchor
          </Button>
        </Card>
      ) : null}
      <div className={styles.viewerScroll} ref={containerRef}>
        <div className={styles.viewerRail} style={{ height: `${totalHeight}px`, width: `${railWidth}px` }}>
          {Array.from({ length: pageCount.value }, (_, index) => {
            const pageNumber = index + 1;
            const top = index * estimatedPageHeight;

            return (
              <div
                className={styles.pageSlot}
                key={pageNumber}
                style={{ height: `${estimatedPageHeight}px`, top: `${top}px`, width: `${railWidth}px` }}
              >
                {visibleSet.has(pageNumber) ? (
                  <PdfPage pageNumber={pageNumber} pdf={pdf} scale={effectiveScale} />
                ) : (
                  <div
                    className={styles.pagePlaceholder}
                    style={{ height: `${estimatedPageHeight - 16}px`, width: `${estimatedPageWidth}px` }}
                  >
                    <Text tone="tertiary">Page {pageNumber}</Text>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
