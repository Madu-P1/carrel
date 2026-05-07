import { useEffect, useState } from "preact/hooks";

import { Text } from "@/design-system";
import { documents } from "@/services/api/endpoints";

import styles from "./DocxReader.module.css";

interface DocxReaderProps {
  docId: string;
}

type LoadState =
  | { status: "loading" }
  | { status: "ready"; html: string }
  | { status: "error"; message: string };

/**
 * Word-style read-only viewer.
 *
 * Strategy: fetch the original .docx blob from the backend, run it
 * through `mammoth` in the browser to produce semantic HTML (headings,
 * lists, tables, bold/italic/links), then render that HTML inside a
 * page-styled container so it reads like a Word document.
 *
 * `mammoth` is dynamically imported so the parser (~500 KB) only loads
 * when a user actually opens a Word file. The chunks-based plain-text
 * view (NonPdfReader) remains the fallback for citation-flight anchored
 * navigation; this is the visual default for .doc / .docx.
 */
export function DocxReader({ docId }: DocxReaderProps) {
  const [state, setState] = useState<LoadState>({ status: "loading" });

  useEffect(() => {
    let cancelled = false;
    setState({ status: "loading" });

    (async () => {
      try {
        const response = await fetch(documents.fileUrl(docId));
        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }
        const buffer = await response.arrayBuffer();
        const mammoth = await import("mammoth");
        const result = await mammoth.convertToHtml({ arrayBuffer: buffer });
        if (cancelled) return;
        setState({ status: "ready", html: result.value });
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setState({ status: "error", message });
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [docId]);

  if (state.status === "loading") {
    return (
      <div className={styles.page}>
        <div className={styles.skeleton}>
          <div className={styles.skeletonLine} style={{ width: "65%" }} />
          <div className={styles.skeletonLine} style={{ width: "92%" }} />
          <div className={styles.skeletonLine} style={{ width: "88%" }} />
          <div className={styles.skeletonLine} style={{ width: "45%" }} />
        </div>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.page}>
        <Text tone="danger">Could not render this document: {state.message}</Text>
        <Text tone="secondary" style={{ marginTop: 12 }}>
          Falling back to plain-text view is available in the source panel.
        </Text>
      </div>
    );
  }

  // mammoth output is sanitized HTML structure (h1-h6, p, ul/ol/li,
  // table/thead/tbody/tr/td, strong, em, a). It does not include scripts
  // or inline event handlers, so dangerouslySetInnerHTML here is the
  // standard pattern documented in mammoth's README.
  return (
    <div className={styles.page}>
      <div
        className={styles.body}
        // eslint-disable-next-line react/no-danger
        dangerouslySetInnerHTML={{ __html: state.html }}
      />
    </div>
  );
}
