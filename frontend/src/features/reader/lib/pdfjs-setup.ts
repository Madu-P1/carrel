import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

declare global {
  interface Window {
    /** Set by `frontend/scripts/build-macos.mjs` before the inlined entry JS.
     *  Dynamic chunks and the PDF.js worker resolve against this directory
     *  when the bundled WKWebView page is loaded from file://. */
    __carrelAssetBase?: string;
    /** Optional override for older/debug bundles that still inject a blob URL. */
    __carrelPdfWorkerUrl?: string;
  }
}

type PdfJsModule = typeof import("pdfjs-dist");

let pdfJsPromise: Promise<PdfJsModule> | null = null;

function resolvePdfWorkerUrl(): string {
  if (window.__carrelPdfWorkerUrl) {
    return window.__carrelPdfWorkerUrl;
  }

  if (window.__carrelAssetBase) {
    return new URL("pdf.worker.min.mjs", window.__carrelAssetBase).href;
  }

  return workerUrl;
}

export async function loadPdfJs(): Promise<PdfJsModule> {
  if (!pdfJsPromise) {
    pdfJsPromise = import("pdfjs-dist").then((module) => {
      module.GlobalWorkerOptions.workerSrc = resolvePdfWorkerUrl();
      return module;
    });
  }

  return pdfJsPromise;
}
