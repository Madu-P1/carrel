import { signal } from "@preact/signals";

export type ReaderFitMode = "custom" | "fit-page" | "fit-width";

export const readerState = {
  currentPage: signal(1),
  requestedPage: signal<number | null>(null),
  scale: signal(1),
  fitMode: signal<ReaderFitMode>("fit-width"),
  outlineOpen: signal(true),
  totalPages: signal(0),
  highlightedChunkId: signal<string | null>(null),
  selectedText: signal("")
};

export function resetReaderState(): void {
  readerState.currentPage.value = 1;
  readerState.requestedPage.value = null;
  readerState.scale.value = 1;
  readerState.fitMode.value = "fit-width";
  readerState.outlineOpen.value = true;
  readerState.totalPages.value = 0;
  readerState.highlightedChunkId.value = null;
  readerState.selectedText.value = "";
}

export function setReaderScale(scale: number): void {
  readerState.fitMode.value = "custom";
  readerState.scale.value = Math.min(3, Math.max(0.4, Number(scale.toFixed(2))));
}

export function setReaderFitMode(mode: ReaderFitMode): void {
  readerState.fitMode.value = mode;
}

export function requestReaderPage(page: number): void {
  const maxPage = readerState.totalPages.value > 0 ? readerState.totalPages.value : page;
  const bounded = Math.max(1, Math.min(maxPage, page));
  readerState.requestedPage.value = bounded;
}

export function zoomReaderBy(delta: number): void {
  setReaderScale(readerState.scale.value + delta);
}
