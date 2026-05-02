import { signal } from "@preact/signals";

export type ReaderFitMode = "custom" | "fit-page" | "fit-width";

const OUTLINE_WIDTH_KEY = "carrel.reader.outline-width";
const RESTORE_KEY_PREFIX = "carrel.reader.restore.";

export interface ReaderRestorationState {
  fitMode: ReaderFitMode;
  outlineOpen: boolean;
  page: number;
  scale: number;
  scrollTop: number;
  updatedAt: string;
}

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

function clampScale(scale: number): number {
  return Math.min(3, Math.max(0.4, Number(scale.toFixed(2))));
}

function clampPage(page: number): number {
  if (!Number.isFinite(page)) return 1;
  const maxPage = readerState.totalPages.value > 0 ? readerState.totalPages.value : page;
  return Math.max(1, Math.min(maxPage, Math.round(page)));
}

function restoreKey(docId: string): string {
  return `${RESTORE_KEY_PREFIX}${encodeURIComponent(docId)}`;
}

function normalizeFitMode(value: unknown): ReaderFitMode {
  return value === "custom" || value === "fit-page" || value === "fit-width"
    ? value
    : "fit-width";
}

export const readerState = {
  currentPage: signal(1),
  requestedPage: signal<number | null>(null),
  scale: signal(1),
  fitMode: signal<ReaderFitMode>("fit-width"),
  findRequestSerial: signal(0),
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
  readerState.findRequestSerial.value = 0;
  readerState.focusMode.value = false;
  readerState.focusAvailable.value = false;
  readerState.outlineOpen.value = true;
  readerState.totalPages.value = 0;
  readerState.highlightedChunkId.value = null;
  readerState.selectedText.value = "";
}

export function setReaderScale(scale: number): void {
  readerState.fitMode.value = "custom";
  readerState.scale.value = clampScale(scale);
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

export function setReaderCurrentPage(page: number): void {
  readerState.currentPage.value = clampPage(page);
}

export function requestReaderPage(page: number): void {
  const bounded = clampPage(page);
  readerState.requestedPage.value = bounded;
}

export function requestReaderFind(): void {
  readerState.findRequestSerial.value += 1;
}

export function toggleReaderOutline(): void {
  readerState.outlineOpen.value = !readerState.outlineOpen.value;
}

export function readReaderRestorationState(docId: string): ReaderRestorationState | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(restoreKey(docId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ReaderRestorationState>;
    const page = Number(parsed.page);
    const scale = Number(parsed.scale);
    const scrollTop = Number(parsed.scrollTop);
    return {
      fitMode: normalizeFitMode(parsed.fitMode),
      outlineOpen: typeof parsed.outlineOpen === "boolean" ? parsed.outlineOpen : true,
      page: Number.isFinite(page) ? Math.max(1, Math.round(page)) : 1,
      scale: Number.isFinite(scale) ? clampScale(scale) : 1,
      scrollTop: Number.isFinite(scrollTop) ? Math.max(0, scrollTop) : 0,
      updatedAt: typeof parsed.updatedAt === "string" ? parsed.updatedAt : ""
    };
  } catch {
    return null;
  }
}

export function restoreReaderState(restored: ReaderRestorationState): void {
  readerState.currentPage.value = clampPage(restored.page);
  readerState.requestedPage.value = clampPage(restored.page);
  readerState.fitMode.value = restored.fitMode;
  readerState.scale.value = clampScale(restored.scale);
  readerState.outlineOpen.value = restored.outlineOpen;
}

export function persistReaderRestorationState(
  docId: string,
  partial: Partial<Omit<ReaderRestorationState, "updatedAt">>
): void {
  if (typeof window === "undefined") return;
  const previous = readReaderRestorationState(docId);
  const next: ReaderRestorationState = {
    fitMode: normalizeFitMode(partial.fitMode ?? previous?.fitMode ?? readerState.fitMode.value),
    outlineOpen: typeof partial.outlineOpen === "boolean"
      ? partial.outlineOpen
      : previous?.outlineOpen ?? readerState.outlineOpen.value,
    page: clampPage(Number(partial.page ?? previous?.page ?? readerState.currentPage.value)),
    scale: clampScale(Number(partial.scale ?? previous?.scale ?? readerState.scale.value)),
    scrollTop: Math.max(0, Number(partial.scrollTop ?? previous?.scrollTop ?? 0)),
    updatedAt: new Date().toISOString()
  };
  try {
    window.localStorage.setItem(restoreKey(docId), JSON.stringify(next));
  } catch {
    // Restoration is a comfort feature. The live reader state still works
    // if WebView storage is unavailable.
  }
}

export function zoomReaderBy(delta: number): void {
  setReaderScale(readerState.scale.value + delta);
}
