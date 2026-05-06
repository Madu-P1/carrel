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

// eslint-disable-next-line @typescript-eslint/consistent-type-imports
type PdfJsModule = typeof import("pdfjs-dist");

let pdfJsPromise: Promise<PdfJsModule> | null = null;

async function resolvePdfWorkerUrl(): Promise<string> {
  if (window.__carrelPdfWorkerUrl) {
    return window.__carrelPdfWorkerUrl;
  }

  if (window.__carrelAssetBase) {
    return new URL("pdf.worker.min.mjs", window.__carrelAssetBase).href;
  }

  const workerModule = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  return workerModule.default;
}

export async function loadPdfJs(): Promise<PdfJsModule> {
  if (!pdfJsPromise) {
    pdfJsPromise = Promise.all([import("pdfjs-dist"), resolvePdfWorkerUrl()]).then(([module, workerUrl]) => {
      module.GlobalWorkerOptions.workerSrc = workerUrl;
      return module;
    });
  }

  return pdfJsPromise;
}
