import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Icon } from "@/design-system";
import type { DocumentDetail } from "@/services/api/endpoints";

import { readerState, requestReaderPage } from "../state";
import styles from "./PdfSearchBar.module.css";

type ReaderChunk = NonNullable<DocumentDetail["chunks"]>[number];

interface PdfSearchBarProps {
  chunks: ReaderChunk[];
  open: boolean;
  onClose: () => void;
}

/**
 * In-document search for the Reader.
 *
 * We search chunks, not pdfjs's text layer, for two reasons:
 *   1. Chunks cover the WHOLE document regardless of which pages pdfjs has
 *      virtualized into the DOM. pdfjs's FindController only sees pages that
 *      have been rendered; on a 400-page PDF that defeats the feature.
 *   2. Chunks already carry page/section metadata and are the same entity
 *      the SM-2 citation flight lands on. Reusing them means search hits
 *      flow through the same scroll-and-highlight machinery as citations.
 *
 * Trade-off: we search against the extracted chunk text, not the raw page
 * stream. If extraction missed something, search won't find it. That's the
 * same blind spot tutor answers already have, so no new surprise here.
 */
export function PdfSearchBar({ chunks, open, onClose }: PdfSearchBarProps) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);

  // Focus the input every time the bar opens so the user can type
  // immediately. Also reset index so the next search starts from the top.
  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      inputRef.current?.select();
      setIndex(0);
    }
  }, [open]);

  const normalized = query.trim().toLowerCase();
  const matches = useMemo(() => {
    if (!normalized) return [] as ReaderChunk[];
    return chunks.filter((c) => (c.content ?? "").toLowerCase().includes(normalized));
  }, [chunks, normalized]);

  // When matches change (new query, different doc), clamp index to the
  // available range and jump to whatever the current head match is.
  useEffect(() => {
    if (matches.length === 0) return;
    const safeIndex = Math.min(index, matches.length - 1);
    if (safeIndex !== index) setIndex(safeIndex);
    const match = matches[safeIndex];
    if (match) {
      readerState.highlightedChunkId.value = match.id;
      if (match.page_num != null) requestReaderPage(match.page_num);
    }
  }, [matches, index]);

  if (!open) return null;

  const step = (direction: 1 | -1) => {
    if (matches.length === 0) return;
    setIndex((prev) => {
      const next = prev + direction;
      if (next < 0) return matches.length - 1;
      if (next >= matches.length) return 0;
      return next;
    });
  };

  const handleKeyDown = (e: KeyboardEvent) => {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
      return;
    }
    if (e.key === "Enter") {
      e.preventDefault();
      step(e.shiftKey ? -1 : 1);
      return;
    }
    if (e.key === "ArrowDown") {
      e.preventDefault();
      step(1);
      return;
    }
    if (e.key === "ArrowUp") {
      e.preventDefault();
      step(-1);
    }
  };

  const counter = (() => {
    if (!normalized) return "";
    if (matches.length === 0) return "No matches";
    return `${index + 1} of ${matches.length}`;
  })();

  return (
    <div className={styles.bar} role="search">
      <label className={styles.field}>
        <span aria-hidden className={styles.icon}>
          <Icon name="search" />
        </span>
        <input
          aria-label="Find in document"
          className={styles.input}
          onInput={(e) => {
            setQuery((e.currentTarget as HTMLInputElement).value);
            setIndex(0);
          }}
          onKeyDown={handleKeyDown}
          placeholder="Find in document"
          ref={inputRef}
          type="search"
          value={query}
        />
      </label>
      <span aria-live="polite" className={styles.counter}>
        {counter}
      </span>
      <div className={styles.controls}>
        <button
          aria-label="Previous match"
          className={styles.stepBtn}
          disabled={matches.length === 0}
          onClick={() => step(-1)}
          type="button"
        >
          <Icon name="chevron-up" />
        </button>
        <button
          aria-label="Next match"
          className={styles.stepBtn}
          disabled={matches.length === 0}
          onClick={() => step(1)}
          type="button"
        >
          <Icon name="chevron-down" />
        </button>
        <button
          aria-label="Close search"
          className={styles.closeBtn}
          onClick={onClose}
          type="button"
        >
          <Icon name="x" />
        </button>
      </div>
    </div>
  );
}
