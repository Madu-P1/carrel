import { useEffect, useRef, useState } from "preact/hooks";

import type { PDFDocumentProxy } from "pdfjs-dist/types/src/display/api";

import { Spinner } from "@/design-system";

import { loadPdfJs } from "../lib/pdfjs-setup";
import styles from "../ReaderView.module.css";

interface PdfPageProps {
  pageNumber: number;
  pdf: PDFDocumentProxy;
  scale: number;
}

export function PdfPage({ pageNumber, pdf, scale }: PdfPageProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const textLayerRef = useRef<HTMLDivElement>(null);
  const [rendered, setRendered] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setRendered(false);

    const render = async () => {
      const pdfjsLib = await loadPdfJs();
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale });
      const textViewport = viewport.clone({ dontFlip: true });

      if (cancelled || !canvasRef.current) {
        return;
      }

      const outputScale = window.devicePixelRatio || 1;
      const canvas = canvasRef.current;
      const context = canvas.getContext("2d");
      if (!context) {
        return;
      }

      canvas.width = Math.floor(viewport.width * outputScale);
      canvas.height = Math.floor(viewport.height * outputScale);
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      context.setTransform(outputScale, 0, 0, outputScale, 0, 0);

      if (textLayerRef.current) {
        textLayerRef.current.innerHTML = "";
        textLayerRef.current.style.width = `${viewport.width}px`;
        textLayerRef.current.style.height = `${viewport.height}px`;
      }

      await page.render({ canvasContext: context, viewport }).promise;

      if (cancelled || !textLayerRef.current) {
        return;
      }

      const textLayer = new pdfjsLib.TextLayer({
        container: textLayerRef.current,
        textContentSource: await page.getTextContent(),
        viewport: textViewport
      });
      await textLayer.render();

      if (!cancelled) {
        setRendered(true);
      }
    };

    void render();

    return () => {
      cancelled = true;
    };
  }, [pageNumber, pdf, scale]);

  return (
    <div className={styles.pageCard} data-page-number={pageNumber}>
      <canvas className={styles.pageCanvas} ref={canvasRef} />
      <div className={styles.textLayer} ref={textLayerRef} />
      {!rendered ? (
        <div className={styles.pageSpinner}>
          <Spinner label={`Rendering page ${pageNumber}`} size={20} />
        </div>
      ) : null}
    </div>
  );
}
