import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

declare global {
  interface Window {
    __einsteinPdfWorkerUrl?: string;
  }
}

type PdfJsModule = typeof import("pdfjs-dist");

let pdfJsPromise: Promise<PdfJsModule> | null = null;

export async function loadPdfJs(): Promise<PdfJsModule> {
  if (!pdfJsPromise) {
    pdfJsPromise = import("pdfjs-dist").then((module) => {
      module.GlobalWorkerOptions.workerSrc = window.__einsteinPdfWorkerUrl ?? workerUrl;
      return module;
    });
  }

  return pdfJsPromise;
}
