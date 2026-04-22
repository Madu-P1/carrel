import { useEffect, useState } from "preact/hooks";

import { appShell, clearRightPanelContent } from "@/app/shell/useAppShell";
import { documents } from "@/services/api/endpoints";
import { Badge, Stack, Text } from "@/design-system";

import { useCardFlight } from "./hooks/useCardFlight";
import { useChunkDeepLink } from "./hooks/useChunkDeepLink";
import { useCitationFlight } from "./hooks/useCitationFlight";
import { usePdfDocument } from "./hooks/usePdfDocument";
import { useReaderDetail } from "./hooks/useReaderDetail";
import { resetReaderState } from "./state";
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
  const pdfState = usePdfDocument(fileUrl);
  const [searchOpen, setSearchOpen] = useState(false);
  // SM-1: if the user arrived via Library card click, FLIP the header into
  // place from the card's source rect.
  const headerRef = useCardFlight<HTMLDivElement>(id);
  // SM-2: if the user arrived via citation chip click, spawn a ghost and
  // animate it to the target chunk.
  useCitationFlight(id, chunkId);

  useEffect(() => {
    resetReaderState();
  }, [id]);

  useChunkDeepLink(chunkId, chunks);

  useEffect(() => {
    if (!detail) {
      return;
    }

    appShell.rightPanelContent.value = <SourcePanel detail={detail} docId={id} />;
    return () => {
      clearRightPanelContent();
    };
  }, [detail, id]);

  // ⌘/ opens the in-doc search. We use ⌘/ instead of ⌘F because ⌘F is owned
  // by WKWebView / the macOS Edit menu; intercepting it cleanly would need
  // Swift-side menu routing. `/` alone is already bound at the AppShell level
  // to jump to Ask. Cmd+Slash is unused elsewhere and keeps the search
  // affordance local to the Reader.
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
    return <ReaderLoadingState />;
  }

  if (error.value) {
    return <ReaderErrorState error={error.value} onRetry={() => void refetch()} />;
  }

  if (!detail || !document) {
    return <ReaderPlaceholder reason="not-found" />;
  }

  const pageCount = document.page_count ?? detail.counts?.chunks ?? 0;

  if (!isPdf) {
    return (
      <Stack className={styles.reader} gap={4}>
        <div className={styles.readerHeader} ref={headerRef}>
          <Stack gap={2}>
            <Badge tone="info">Reader</Badge>
            <Text as="h2" variant="h1" weight="bold">
              {document.filename}
            </Text>
            <Text tone="secondary">
              {chunks.length} chunks • plain-text source rendering
            </Text>
          </Stack>
        </div>
        <NonPdfReader chunks={chunks} />
      </Stack>
    );
  }

  return (
    <Stack className={styles.reader} gap={4}>
      <div className={styles.readerHeader}>
        <Stack gap={2}>
          <Badge tone="info">Reader</Badge>
          <Text as="h2" variant="h1" weight="bold">
            {document.filename}
          </Text>
          <Text tone="secondary">
            {pageCount} pages • {detail.summary}
          </Text>
        </Stack>
      </div>
      <div className={styles.readerRoot}>
        <OutlineRail outline={pdfState.outline.value} />
        <div className={styles.readerMain}>
          <PdfToolbar pageCount={pageCount} />
          <PdfSearchBar
            chunks={chunks}
            onClose={() => setSearchOpen(false)}
            open={searchOpen}
          />
          <PdfViewer pdfState={pdfState} />
        </div>
      </div>
    </Stack>
  );
}

export function ReaderView({ chunkId = null, id }: ReaderViewProps) {
  if (!id) {
    return <ReaderPlaceholder reason="no-doc-selected" />;
  }

  return <ReaderDocumentView chunkId={chunkId} id={id} />;
}
