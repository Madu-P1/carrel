import { useEffect, useState } from "preact/hooks";

import { Badge, Button, Stack, Text } from "@/design-system";

import {
  readerState,
  requestReaderPage,
  setReaderFitMode,
  setReaderScale,
  zoomReaderBy
} from "../state";
import styles from "../ReaderView.module.css";

interface PdfToolbarProps {
  pageCount: number;
}

export function PdfToolbar({ pageCount }: PdfToolbarProps) {
  const currentPage = readerState.currentPage.value;
  const fitMode = readerState.fitMode.value;
  const scale = readerState.scale.value;
  const [pageInput, setPageInput] = useState(String(currentPage));

  useEffect(() => {
    setPageInput(String(currentPage));
  }, [currentPage]);

  const commitPage = () => {
    const parsed = Number.parseInt(pageInput, 10);
    if (Number.isNaN(parsed)) {
      setPageInput(String(currentPage));
      return;
    }
    requestReaderPage(parsed);
  };

  return (
    <div className={styles.toolbar}>
      <Stack align="center" direction="horizontal" gap={3} wrap>
        <Badge tone="info">PDF reader</Badge>
        <Button
          aria-label="Previous page"
          disabled={currentPage <= 1}
          onClick={() => requestReaderPage(currentPage - 1)}
          variant="ghost"
        >
          Prev
        </Button>
        <label className={styles.pageField}>
          <span className={styles.pageFieldLabel}>Page</span>
          <input
            className={styles.pageFieldInput}
            max={Math.max(pageCount, 1)}
            min={1}
            onBlur={commitPage}
            onChange={(event) => setPageInput(event.currentTarget.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                commitPage();
              }
            }}
            type="number"
            value={pageInput}
          />
        </label>
        <Text tone="secondary">of {pageCount || 0}</Text>
        <Button
          aria-label="Next page"
          disabled={pageCount === 0 || currentPage >= pageCount}
          onClick={() => requestReaderPage(currentPage + 1)}
          variant="ghost"
        >
          Next
        </Button>
      </Stack>

      <Stack align="center" direction="horizontal" gap={2} wrap>
        <Button aria-label="Zoom out" onClick={() => zoomReaderBy(-0.1)} variant="ghost">
          -
        </Button>
        <Button aria-label="Reset zoom" onClick={() => setReaderScale(1)} variant="secondary">
          {Math.round(scale * 100)}%
        </Button>
        <Button aria-label="Zoom in" onClick={() => zoomReaderBy(0.1)} variant="ghost">
          +
        </Button>
        <Button
          onClick={() => setReaderFitMode("fit-page")}
          variant={fitMode === "fit-page" ? "primary" : "ghost"}
        >
          Fit page
        </Button>
        <Button
          onClick={() => setReaderFitMode("fit-width")}
          variant={fitMode === "fit-width" ? "primary" : "ghost"}
        >
          Fit width
        </Button>
      </Stack>
    </div>
  );
}
