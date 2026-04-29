import workerUrl from "pdfjs-dist/build/pdf.worker.min.mjs?url";

declare global {
  interface Window {
    /** Set by the bundled-app worker shim in `frontend/scripts/build-macos.mjs`.
     *  Points pdfjs at an in-memory blob:// URL so the worker loads even when
     *  the parent page is at file://. Renamed from __einsteinPdfWorkerUrl in
     *  the 2026-04-29 Carrel rename — both sides of this contract live in
     *  this repo, so the rename is safe without a backward-compat shim. */
    __carrelPdfWorkerUrl?: string;
  }
}

type PdfJsModule = typeof import("pdfjs-dist");

let pdfJsPromise: Promise<PdfJsModule> | null = null;

export async function loadPdfJs(): Promise<PdfJsModule> {
  if (!pdfJsPromise) {
    pdfJsPromise = import("pdfjs-dist").then((module) => {
      module.GlobalWorkerOptions.workerSrc = window.__carrelPdfWorkerUrl ?? workerUrl;
      return module;
    });
  }

  return pdfJsPromise;
}
