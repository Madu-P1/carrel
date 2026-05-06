import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import {
  appShell,
  clearRightPanelContent,
  rememberReaderDocument,
  toggleLeft,
  toggleRight
} from "@/app/shell/useAppShell";
import { Stack, Text } from "@/design-system";
import { documents, evidence, type EvidenceResolution } from "@/services/api/endpoints";
import { events } from "@/services/metrics/events";

import { NonPdfReader } from "./components/NonPdfReader";
import { OutlineRail } from "./components/OutlineRail";
import { PdfSearchBar } from "./components/PdfSearchBar";
import { PdfToolbar } from "./components/PdfToolbar";
import { PdfViewer } from "./components/PdfViewer";
import { ReaderErrorState } from "./components/ReaderErrorState";
import { ReaderLoadingState } from "./components/ReaderLoadingState";
import { ReaderPlaceholder } from "./components/ReaderPlaceholder";
import { SourcePanel } from "./components/source-panel/SourcePanel";
import { useCardFlight } from "./hooks/useCardFlight";
import { useChunkDeepLink } from "./hooks/useChunkDeepLink";
import { useCitationFlight } from "./hooks/useCitationFlight";
import { usePdfDocument } from "./hooks/usePdfDocument";
import { useReaderDetail } from "./hooks/useReaderDetail";
import styles from "./ReaderView.module.css";
import {
  persistReaderRestorationState,
  readerState,
  readReaderRestorationState,
  resetReaderState,
  restoreReaderState,
  setReaderFocusAvailable,
  toggleReaderOutline
} from "./state";

interface ReaderViewProps {
  id?: string;
  chunkId?: string | null;
}

function ReaderDocumentView({ chunkId = null, id }: { chunkId?: string | null; id: string }) {
  const { data, error, loading, refetch } = useReaderDetail(id);
  const detail = data.value;
  const document = detail?.document;
  const chunks = detail?.chunks ?? [];
  const isPdf = document?.file_type?.toLowerCase() === "pdf";
  const fileUrl = isPdf ? documents.fileUrl(id) : null;
  const pdfState = usePdfDocument(fileUrl, chunks);
  const [searchOpen, setSearchOpen] = useState(false);
  const [selectedEvidence, setSelectedEvidence] = useState<EvidenceResolution | null>(null);
  const findRequestSerial = readerState.findRequestSerial.value;
  const focusMode = readerState.focusMode.value;
  const leftPanelOpen = appShell.leftOpen.value;
  const outlineOpen = readerState.outlineOpen.value;
  const rightPanelOpen = appShell.rightOpen.value;
  const restoredReaderRef = useRef<string | null>(null);
  const preFocusChromeRef = useRef<{
    leftOpen: boolean;
    outlineOpen: boolean;
    rightOpen: boolean;
  } | null>(null);

  // SM-1: if the user arrived via Library card click, FLIP this element
  // from the card's source rect. The ref now lives on the toolbar (PDF
  // path) or on a compact header (non-PDF path). We build a usePdf=true
  // ref and a usePdf=false ref and attach whichever path renders.
  const toolbarFlightRef = useCardFlight<HTMLDivElement>(id);
  const headerFlightRef = useCardFlight<HTMLDivElement>(id);
  const openSearch = useCallback((mode: "keyboard" | "menu" | "toolbar") => {
    setSearchOpen(true);
    void events.track("reader.find_used", { mode }, "reader");
  }, []);

  // SM-2: if the user arrived via citation chip click, spawn a ghost and
  // animate it to the target chunk.
  useCitationFlight(id, chunkId);

  useEffect(() => {
    restoredReaderRef.current = null;
    resetReaderState();
    rememberReaderDocument(id);
  }, [id]);

  useEffect(() => {
    setReaderFocusAvailable(Boolean(detail && isPdf));
    return () => setReaderFocusAvailable(false);
  }, [detail, isPdf]);

  useEffect(() => {
    if (!detail || !isPdf || restoredReaderRef.current === id) {
      return;
    }
    const restored = readReaderRestorationState(id);
    if (restored) {
      restoreReaderState(restored);
    }
    restoredReaderRef.current = id;
  }, [detail, id, isPdf]);

  useEffect(() => {
    if (!detail || !isPdf || restoredReaderRef.current !== id || focusMode) {
      return;
    }
    persistReaderRestorationState(id, {
      outlineOpen
    });
  }, [
    detail,
    focusMode,
    id,
    isPdf,
    outlineOpen
  ]);

  useEffect(() => {
    if (focusMode) {
      if (!preFocusChromeRef.current) {
        preFocusChromeRef.current = {
          leftOpen: appShell.leftOpen.value,
          outlineOpen: readerState.outlineOpen.value,
          rightOpen: appShell.rightOpen.value
        };
      }
      appShell.leftOpen.value = false;
      appShell.rightOpen.value = false;
      readerState.outlineOpen.value = false;
      return undefined;
    }

    if (preFocusChromeRef.current) {
      const previous = preFocusChromeRef.current;
      appShell.leftOpen.value = previous.leftOpen;
      appShell.rightOpen.value = previous.rightOpen;
      readerState.outlineOpen.value = previous.outlineOpen;
      preFocusChromeRef.current = null;
    }

    return undefined;
  }, [focusMode]);

  useEffect(() => {
    return () => {
      const previous = preFocusChromeRef.current;
      if (previous) {
        appShell.leftOpen.value = previous.leftOpen;
        appShell.rightOpen.value = previous.rightOpen;
        readerState.outlineOpen.value = previous.outlineOpen;
      }
      readerState.focusMode.value = false;
    };
  }, []);

  useChunkDeepLink(chunkId, chunks);

  useEffect(() => {
    if (!chunkId || !detail) {
      setSelectedEvidence(null);
      return;
    }
    let cancelled = false;
    void evidence.resolve({ documentId: id, chunkId })
      .then((resolved) => {
        if (!cancelled) setSelectedEvidence(resolved);
      })
      .catch(() => {
        if (!cancelled) setSelectedEvidence(null);
      });
    return () => {
      cancelled = true;
    };
  }, [chunkId, detail, id]);

  useEffect(() => {
    if (!detail) {
      return;
    }

    appShell.rightPanelContent.value = (
      <SourcePanel detail={detail} docId={id} selectedEvidence={selectedEvidence} />
    );
    return () => {
      clearRightPanelContent();
    };
  }, [detail, id, selectedEvidence]);

  useEffect(() => {
    if (!isPdf || findRequestSerial === 0) return;
    openSearch("menu");
  }, [findRequestSerial, isPdf, openSearch]);

  // Native Edit > Find in Reader dispatches reader.find, while Cmd+F and
  // Cmd+/ both open the in-doc search from the web layer. Plain "/" stays
  // global and jumps to Ask.
  useEffect(() => {
    if (!isPdf) return;
    const onKeyDown = (e: KeyboardEvent) => {
      const key = e.key.toLowerCase();
      if (!(key === "/" || key === "f") || !(e.metaKey || e.ctrlKey)) return;
      if (e.shiftKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName;
      if (target?.isContentEditable || tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      e.preventDefault();
      openSearch("keyboard");
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isPdf, openSearch]);

  if (loading.value && !detail) {
    return <ReaderLoadingState filename={document?.filename} />;
  }

  if (error.value) {
    return <ReaderErrorState error={error.value} onRetry={() => void refetch()} />;
  }

  if (!detail || !document) {
    return <ReaderPlaceholder reason="not-found" />;
  }

  const pageCount = document.page_count ?? detail.counts?.chunks ?? 0;
  const filename = document.filename ?? "Untitled";
  const fileType = document.file_type ?? "FILE";

  // ---- Non-PDF branch: plain-text view with a page-heading block -----
  //
  // Non-PDF sources keep the old hero header because there's no toolbar
  // to absorb the title. SM-1 card flight lands on this header.
  if (!isPdf) {
    return (
      <div className={styles.reader}>
        <header className={styles.nonPdfHeader} ref={headerFlightRef}>
          <Stack gap={2}>
            <span className={styles.readerEyebrow}>Reader</span>
            <h1 className={styles.readerHeading}>{filename}</h1>
            <Text tone="secondary">
              {chunks.length} chunk{chunks.length === 1 ? "" : "s"} · plain-text rendering
            </Text>
          </Stack>
        </header>
        <NonPdfReader chunks={chunks} docId={id} />
      </div>
    );
  }

  // ---- PDF branch: three-column shell with the toolbar owning the title.
  return (
    <div
      className={[styles.reader, focusMode ? styles.readerFocus : ""].filter(Boolean).join(" ")}
      data-focus-mode={focusMode ? "true" : "false"}
      data-testid="pdf-reader"
    >
      <div className={[styles.readerRoot, focusMode ? styles.readerRootFocus : ""].filter(Boolean).join(" ")}>
        <OutlineRail outline={pdfState.outline.value} />
        <div className={[styles.readerMain, focusMode ? styles.readerMainFocus : ""].filter(Boolean).join(" ")}>
          <PdfToolbar
            filename={filename}
            fileType={fileType}
            flightRef={toolbarFlightRef}
            leftPanelOpen={leftPanelOpen}
            onOpenSearch={() => openSearch("toolbar")}
            onToggleAppSidebar={toggleLeft}
            onToggleOutline={toggleReaderOutline}
            onToggleSourcePanel={toggleRight}
            outlineOpen={outlineOpen}
            pageCount={pageCount}
            rightPanelOpen={rightPanelOpen}
          />
          <PdfSearchBar
            chunks={chunks}
            onClose={() => setSearchOpen(false)}
            open={searchOpen}
          />
          <div className={[styles.canvasWrap, focusMode ? styles.canvasWrapFocus : ""].filter(Boolean).join(" ")}>
            <PdfViewer docId={id} pdfState={pdfState} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function ReaderView({ chunkId = null, id }: ReaderViewProps) {
  const resolvedId = id ?? appShell.lastReaderDocumentId.value ?? undefined;

  if (!resolvedId) {
    return <ReaderPlaceholder reason="no-doc-selected" />;
  }

  // key ensures the whole subtree remounts on doc change so hooks
  // restart cleanly (was silently working before because internal
  // state reset fired on id change).
  return <ReaderDocumentView chunkId={chunkId} id={resolvedId} key={resolvedId} />;
}

// Legacy named export retained so useCardFlight import paths stay stable
// if anything else imports the component by position.
export const ReaderDocumentViewForTests = ReaderDocumentView;
