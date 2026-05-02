import { useEffect, useRef, useState } from "preact/hooks";

import type {
  PDFDocumentProxy,
  RenderTask
} from "pdfjs-dist/types/src/display/api";

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
    let renderTask: RenderTask | null = null;
    setRendered(false);

    const render = async () => {
      const pdfjsLib = await loadPdfJs();
      const page = await pdf.getPage(pageNumber);
      const viewport = page.getViewport({ scale });

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
        textLayerRef.current.style.setProperty("--scale-factor", String(viewport.scale));
        textLayerRef.current.style.width = `${viewport.width}px`;
        textLayerRef.current.style.height = `${viewport.height}px`;
      }

      // Hold the RenderTask so the cleanup can cancel it. The
      // previous "let cancelled = true" pattern aborted BEFORE the
      // render started but couldn't interrupt one in flight; when
      // the effect re-ran (pageNumber/scale changed, parent
      // remounted, etc.), the new render hit the same canvas while
      // the old one was still painting, and pdf.js threw
      // "Cannot use the same canvas during multiple render()
      // operations." page.render() returns a RenderTask with both
      // a .promise and a .cancel() — using both is what the docs
      // recommend.
      renderTask = page.render({ canvasContext: context, viewport });
      try {
        await renderTask.promise;
      } catch (err) {
        // pdf.js throws RenderingCancelledException on cancel; that's
        // expected, swallow it. Anything else, propagate.
        const name = (err as { name?: string } | null)?.name;
        if (name === "RenderingCancelledException") return;
        throw err;
      } finally {
        renderTask = null;
      }

      if (cancelled || !textLayerRef.current) {
        return;
      }

      const textLayer = new pdfjsLib.TextLayer({
        container: textLayerRef.current,
        textContentSource: await page.getTextContent(),
        viewport
      });
      await textLayer.render();

      if (!cancelled) {
        setRendered(true);
      }
    };

    void render();

    return () => {
      cancelled = true;
      // Signal pdf.js to abort the in-flight render. The await in
      // render() will reject with RenderingCancelledException, which
      // we catch above. Without this, the next render() call on the
      // same canvas (after the effect re-runs) would race the still-
      // painting one and throw the [REJECT] error the user saw.
      renderTask?.cancel();
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
