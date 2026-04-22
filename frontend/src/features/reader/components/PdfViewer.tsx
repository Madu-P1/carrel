import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

import { Card, Text } from "@/design-system";

import { usePageVirtualizer } from "../hooks/usePageVirtualizer";
import type { PdfState } from "../hooks/usePdfDocument";
import { useReaderSelection } from "../hooks/useReaderSelection";
import { readerState } from "../state";
import { ReaderErrorState } from "./ReaderErrorState";
import { ReaderLoadingState } from "./ReaderLoadingState";
import { PdfPage } from "./PdfPage";
import styles from "../ReaderView.module.css";

interface PdfViewerProps {
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

export function PdfViewer({ pdfState }: PdfViewerProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const { doc, error, loading, pageCount } = pdfState;
  const fitMode = readerState.fitMode.value;
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
    if (fitMode === "fit-width") {
      return Math.max(0.4, (containerWidth - 48) / Math.max(baseWidth, 1));
    }
    if (fitMode === "fit-page") {
      return Math.max(
        0.4,
        Math.min((containerWidth - 48) / Math.max(baseWidth, 1), (containerHeight - 48) / Math.max(baseHeight, 1))
      );
    }
    return scale;
  }, [baseHeight, baseWidth, containerHeight, containerWidth, fitMode, scale]);

  const estimatedPageHeight = Math.max(320, baseHeight * effectiveScale + 32);
  const estimatedPageWidth = Math.max(240, baseWidth * effectiveScale);
  const { totalHeight, visiblePages } = usePageVirtualizer({
    containerRef,
    pageCount: pageCount.value,
    pageHeight: estimatedPageHeight
  });
  const visibleSet = useMemo(() => new Set(visiblePages), [visiblePages]);

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
            Selection captured for PR-E5: "{selectedText.slice(0, 140)}
            {selectedText.length > 140 ? "..." : ""}"
          </Text>
        </Card>
      ) : null}
      <div className={styles.viewerScroll} ref={containerRef}>
        <div className={styles.viewerRail} style={{ height: `${totalHeight}px` }}>
          {Array.from({ length: pageCount.value }, (_, index) => {
            const pageNumber = index + 1;
            const top = index * estimatedPageHeight;

            return (
              <div
                className={styles.pageSlot}
                key={pageNumber}
                style={{ height: `${estimatedPageHeight}px`, top: `${top}px` }}
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
