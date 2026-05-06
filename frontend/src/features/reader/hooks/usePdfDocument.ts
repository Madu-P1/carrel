import { signal, type Signal } from "@preact/signals";
import type {
  PDFDocumentLoadingTask,
  PDFDocumentProxy,
  RefProxy
} from "pdfjs-dist/types/src/display/api";
import { useEffect, useRef } from "preact/hooks";


import type { DocumentDetail } from "@/services/api/endpoints";

import { loadPdfJs } from "../lib/pdfjs-setup";
import { readerState } from "../state";

interface PdfOutlineItem {
  dest?: string | null | unknown[] | undefined;
  items?: PdfOutlineItem[];
  title?: string;
}

export interface PdfOutlineNode {
  children: PdfOutlineNode[];
  pageNumber: number | null;
  title: string;
}

export interface PdfState {
  doc: Signal<PDFDocumentProxy | null>;
  error: Signal<Error | null>;
  loading: Signal<boolean>;
  outline: Signal<PdfOutlineNode[]>;
  pageCount: Signal<number>;
}

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];
const EMPTY_READER_CHUNKS: ReaderChunk[] = [];

async function resolveDestinationPage(
  pdf: PDFDocumentProxy,
  destination: PdfOutlineItem["dest"]
): Promise<number | null> {
  if (!destination) {
    return null;
  }

  let resolvedDestination: string | unknown[] | null = destination ?? null;
  if (typeof resolvedDestination === "string") {
    resolvedDestination = await pdf.getDestination(resolvedDestination);
  }

  if (!Array.isArray(resolvedDestination) || resolvedDestination.length === 0) {
    return null;
  }

  const target = resolvedDestination[0];
  if (!target || typeof target !== "object") {
    return null;
  }

  try {
    return (await pdf.getPageIndex(target as RefProxy)) + 1;
  } catch {
    return null;
  }
}

async function normalizeOutline(
  pdf: PDFDocumentProxy,
  items: PdfOutlineItem[]
): Promise<PdfOutlineNode[]> {
  return Promise.all(
    items.map(async (item) => ({
      children: await normalizeOutline(pdf, item.items ?? []),
      pageNumber: await resolveDestinationPage(pdf, item.dest),
      title: String(item.title ?? "").trim() || "Untitled section"
    }))
  );
}

function deriveOutlineFromChunks(chunks: ReaderChunk[]): PdfOutlineNode[] {
  const nodes: PdfOutlineNode[] = [];
  let lastKey = "";
  for (const chunk of chunks) {
    const title = (chunk.section || "").trim() || "Source section";
    const key = `${title}::${chunk.page_num ?? ""}`;
    if (key === lastKey) continue;
    lastKey = key;
    nodes.push({
      title,
      pageNumber: chunk.page_num ?? null,
      children: []
    });
  }
  return nodes;
}

export function usePdfDocument(url: string | null, chunks: ReaderChunk[] = EMPTY_READER_CHUNKS): PdfState {
  const stateRef = useRef<PdfState | null>(null);
  if (!stateRef.current) {
    stateRef.current = {
      doc: signal<PDFDocumentProxy | null>(null),
      error: signal<Error | null>(null),
      loading: signal(false),
      outline: signal<PdfOutlineNode[]>([]),
      pageCount: signal(0)
    };
  }

  useEffect(() => {
    const state = stateRef.current;
    if (!state || !url) {
      if (state) {
        state.doc.value = null;
        state.error.value = null;
        state.loading.value = false;
        state.outline.value = [];
        state.pageCount.value = 0;
      }
      readerState.totalPages.value = 0;
      return;
    }

    let disposed = false;
    let task: PDFDocumentLoadingTask | null = null;

    const load = async () => {
      state.loading.value = true;
      state.error.value = null;
      try {
        const pdfjsLib = await loadPdfJs();
        const loadingTask = pdfjsLib.getDocument({
          disableAutoFetch: true,
          disableStream: false,
          url
        });
        task = loadingTask;
        const pdf = await loadingTask.promise;
        if (disposed) {
          void pdf.destroy();
          return;
        }
        const rawOutline = ((await pdf.getOutline()) ?? []) as PdfOutlineItem[];
        state.doc.value = pdf;
        state.pageCount.value = pdf.numPages;
        readerState.totalPages.value = pdf.numPages;
        const normalized = await normalizeOutline(pdf, rawOutline);
        state.outline.value = normalized.length > 0 ? normalized : deriveOutlineFromChunks(chunks);
      } catch (error) {
        if (!disposed) {
          state.error.value = error as Error;
        }
      } finally {
        if (!disposed) {
          state.loading.value = false;
        }
      }
    };

    void load();

    return () => {
      disposed = true;
      state.outline.value = [];
      state.pageCount.value = 0;
      readerState.totalPages.value = 0;
      if (task) {
        void task.destroy();
      }
      if (state.doc.value) {
        void state.doc.value.destroy();
        state.doc.value = null;
      }
    };
  }, [url, chunks]);

  return stateRef.current;
}
