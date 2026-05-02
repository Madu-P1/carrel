import { useEffect, useRef, useState } from "preact/hooks";

import { appShell, clearRightPanelContent, rememberReaderDocument } from "@/app/shell/useAppShell";
import { documents, evidence, type EvidenceResolution } from "@/services/api/endpoints";
import { Stack, Text } from "@/design-system";

import { useCardFlight } from "./hooks/useCardFlight";
import { useChunkDeepLink } from "./hooks/useChunkDeepLink";
import { useCitationFlight } from "./hooks/useCitationFlight";
import { usePdfDocument } from "./hooks/usePdfDocument";
import { useReaderDetail } from "./hooks/useReaderDetail";
import { readerState, resetReaderState, setReaderFocusAvailable } from "./state";
import { NonPdfReader } from "./components/NonPdfReader";
import { OutlineRail } from "./components/OutlineRail";
import { PdfSearchBar } from "./components/PdfSearchBar";
import { PdfToolbar } from "./components/PdfToolbar";
import { PdfViewer } from "./components/PdfViewer";
import { ReaderErrorState } from "./components/ReaderErrorState";
import { ReaderLoadingState } from "./components/ReaderLoadingState";
import { ReaderPlaceholder } from "./components/ReaderPlaceholder";
import { SourcePanel } from "./components/source-panel/SourcePanel";
import styles from "./ReaderView.module.css";

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
  const focusMode = readerState.focusMode.value;
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

  // SM-2: if the user arrived via citation chip click, spawn a ghost and
  // animate it to the target chunk.
  useCitationFlight(id, chunkId);

  useEffect(() => {
    resetReaderState();
    rememberReaderDocument(id);
  }, [id]);

  useEffect(() => {
    setReaderFocusAvailable(Boolean(detail && isPdf));
    return () => setReaderFocusAvailable(false);
  }, [detail, isPdf]);

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

  // ⌘/ opens the in-doc search. ⌘F is owned by WKWebView / the macOS Edit
  // menu; intercepting it cleanly would need Swift-side routing. `/`
  // alone is already bound at the AppShell level to jump to Ask. Cmd+/
  // is unused elsewhere and keeps the search affordance local to the
  // Reader.
  useEffect(() => {
    if (!isPdf) return;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "/" || !(e.metaKey || e.ctrlKey)) return;
      if (e.shiftKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      if (target?.isContentEditable) return;
      e.preventDefault();
      setSearchOpen(true);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [isPdf]);

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
            onOpenSearch={() => setSearchOpen(true)}
            pageCount={pageCount}
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
