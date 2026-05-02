import { signal } from "@preact/signals";

export type ReaderFitMode = "custom" | "fit-page" | "fit-width";

const OUTLINE_WIDTH_KEY = "carrel.reader.outline-width";

export const READER_OUTLINE_WIDTH = {
  collapsed: 48,
  default: 280,
  max: 420,
  min: 220
} as const;

function clampWidth(value: number): number {
  return Math.min(
    READER_OUTLINE_WIDTH.max,
    Math.max(READER_OUTLINE_WIDTH.min, Math.round(value))
  );
}

function readOutlineWidth(): number {
  if (typeof window === "undefined") return READER_OUTLINE_WIDTH.default;
  try {
    const raw = window.localStorage.getItem(OUTLINE_WIDTH_KEY);
    if (!raw) return READER_OUTLINE_WIDTH.default;
    const parsed = Number(raw);
    if (!Number.isFinite(parsed)) return READER_OUTLINE_WIDTH.default;
    return clampWidth(parsed);
  } catch {
    return READER_OUTLINE_WIDTH.default;
  }
}

function writeOutlineWidth(width: number): void {
  try {
    window.localStorage.setItem(OUTLINE_WIDTH_KEY, String(width));
  } catch {
    // Width persistence is best-effort; the signal still updates the UI.
  }
}

export const readerState = {
  currentPage: signal(1),
  requestedPage: signal<number | null>(null),
  scale: signal(1),
  fitMode: signal<ReaderFitMode>("fit-width"),
  focusMode: signal(false),
  focusAvailable: signal(false),
  outlineOpen: signal(true),
  outlineWidth: signal(readOutlineWidth()),
  totalPages: signal(0),
  highlightedChunkId: signal<string | null>(null),
  selectedText: signal("")
};

export function resetReaderState(): void {
  readerState.currentPage.value = 1;
  readerState.requestedPage.value = null;
  readerState.scale.value = 1;
  readerState.fitMode.value = "fit-width";
  readerState.focusMode.value = false;
  readerState.focusAvailable.value = false;
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

export function setReaderFocusMode(enabled: boolean): void {
  readerState.focusMode.value = enabled;
}

export function setReaderFocusAvailable(available: boolean): void {
  readerState.focusAvailable.value = available;
  if (!available) {
    readerState.focusMode.value = false;
  }
}

export function setReaderOutlineWidth(width: number): void {
  const next = clampWidth(width);
  readerState.outlineWidth.value = next;
  writeOutlineWidth(next);
}

export function requestReaderPage(page: number): void {
  const maxPage = readerState.totalPages.value > 0 ? readerState.totalPages.value : page;
  const bounded = Math.max(1, Math.min(maxPage, page));
  readerState.requestedPage.value = bounded;
}

export function zoomReaderBy(delta: number): void {
  setReaderScale(readerState.scale.value + delta);
}
