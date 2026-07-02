/**
 * The DOCX / plain-text pane of the Document Examination overlay.
 *
 * DOCX renders through docx-preview (Apache-2.0, jszip only, zero network):
 * faithful page-shaped HTML from the original bytes, entirely client-side.
 * Plain text renders as a quiet preformatted column. In both, the cited
 * passage is anchored by exact normalized match (domHighlight.ts): found
 * runs get the ink underline, a missing passage gets a visible note, never
 * a fabricated highlight.
 *
 * docx-preview is dynamically imported on first use (user-click path, no
 * render-time Suspense) so the library stays out of the entry bundle and the
 * file:// WKWebView constraint never sees it at boot.
 */
import { useEffect, useRef, useState } from "preact/hooks";

import { Spinner } from "@/design-system";

import { markQuoteInDom } from "./domHighlight";
import { fetchDocumentFile } from "./fetchDocumentFile";
import styles from "./examine.module.css";

interface DocxExaminationProps {
  docId: string;
  kind: "docx" | "txt";
  quote?: string | null;
  /** Reports a load failure to the parent, which owns the named-cause
   *  failure panel and Retry control (DocumentExamination.tsx). */
  onError?: (message: string) => void;
}

type AnchorState = "none" | "searching" | "found" | "absent";

function prefersReducedMotion(): boolean {
  return typeof window.matchMedia === "function"
    ? window.matchMedia("(prefers-reduced-motion: reduce)").matches
    : false;
}

export function DocxExamination({ docId, kind, quote, onError }: DocxExaminationProps) {
  const hostRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [status, setStatus] = useState<"loading" | "ready" | "error">("loading");
  const [anchor, setAnchor] = useState<AnchorState>(quote ? "searching" : "none");

  useEffect(() => {
    let disposed = false;
    setStatus("loading");
    setAnchor(quote ? "searching" : "none");

    void (async () => {
      try {
        const bytes = await fetchDocumentFile(docId);
        if (disposed || !hostRef.current) {
          return;
        }
        const host = hostRef.current;
        host.innerHTML = "";
        if (kind === "docx") {
          const { renderAsync } = await import("docx-preview");
          if (disposed) {
            return;
          }
          await renderAsync(bytes, host, undefined, {
            ignoreLastRenderedPageBreak: false,
            inWrapper: true
          });
        } else {
          const pre = host.ownerDocument.createElement("pre");
          pre.className = styles.textBody;
          pre.textContent = new TextDecoder("utf-8").decode(bytes);
          host.appendChild(pre);
        }
        if (disposed) {
          return;
        }
        setStatus("ready");
        if (quote) {
          const marks = markQuoteInDom(host, quote);
          if (marks && marks.length > 0) {
            setAnchor("found");
            const behavior = prefersReducedMotion() ? "auto" : "smooth";
            // Optional: jsdom (tests) has no scrollIntoView at all, and a
            // missing/no-op implementation must never be misread as the
            // record's bytes having failed to load.
            marks[0].scrollIntoView?.({ behavior, block: "center" });
          } else {
            setAnchor("absent");
          }
        }
      } catch (cause) {
        if (!disposed) {
          const message =
            cause instanceof Error && cause.message
              ? cause.message
              : "The record could not be opened.";
          setStatus("error");
          onError?.(message);
        }
      }
    })();

    return () => {
      disposed = true;
    };
  }, [docId, kind, quote, onError]);

  if (status === "error") {
    // The named-cause failure panel + Retry control render one level up, in
    // DocumentExamination.tsx, once onError has reported this message.
    return null;
  }

  return (
    <div className={styles.docxPane}>
      {anchor === "searching" || anchor === "found" || anchor === "absent" ? (
        <div className={styles.docxToolbar}>
          <span className={styles.anchorStatus} role="status">
            {anchor === "searching" ? (
              <span className={styles.anchorNote}>Locating the cited passage…</span>
            ) : anchor === "found" ? (
              <span className={styles.anchorNote}>Cited passage anchored below.</span>
            ) : (
              <span className={styles.anchorNoteAbsent}>
                Could not locate the cited passage in this record.
              </span>
            )}
          </span>
        </div>
      ) : null}
      {status === "loading" ? (
        <div className={styles.paneMessage}>
          <Spinner size={16} />
          <span>Opening the record…</span>
        </div>
      ) : null}
      <div className={styles.docxScroll} ref={scrollRef} hidden={status !== "ready"}>
        <div className={styles.docxHost} ref={hostRef} />
      </div>
    </div>
  );
}
