/**
 * The Document Examination overlay: the original record, opened in place.
 *
 * An overlay, not a route, for the same reason as SourcePassageOverlay: the
 * Cachet shell unmounts views on navigation, and routing away from a live
 * verification to look at the record would discard an unsaved verdict. The
 * overlay mounts once at the CachetApp level, driven by the module-scope
 * `examination` signal, so it survives rail clicks and any surface can open
 * it: the Examination drawer's cited sources land on the cited passage; the
 * Vault opens a record plain.
 *
 * Dispatch is by the engine's file_type, resolved from the engine when the
 * caller does not know it. Types Cachet cannot faithfully display get an
 * honest refusal naming the type, never a degraded approximation.
 */
import { useEffect, useState } from "preact/hooks";

import { Spinner, useModalDialog } from "@/design-system";
import { documents } from "@/services/api/endpoints";
import verifyStyles from "@/features/verify/VerifyView.module.css";

import { DocxExamination } from "./DocxExamination";
import { closeExamination, examination, examinationHostMounted } from "./examineStore";
import { PdfExamination } from "./PdfExamination";
import styles from "./examine.module.css";

type PaneKind = "pdf" | "docx" | "txt" | "unsupported";

function paneKindFor(fileType: string): PaneKind {
  const ft = fileType.trim().toLowerCase();
  if (ft.includes("pdf")) {
    return "pdf";
  }
  if (ft.includes("docx")) {
    return "docx";
  }
  if (ft === "txt" || ft === "md" || ft === "text" || ft.startsWith("text/")) {
    return "txt";
  }
  return "unsupported";
}

export function DocumentExamination() {
  const request = examination.value;
  const [resolvedType, setResolvedType] = useState<string | null>(null);
  const [resolveFailed, setResolveFailed] = useState(false);

  const docId = request?.docId ?? null;
  const knownType = request?.fileType ?? null;

  // aria-modal=true. One hook owns the whole modal lifecycle in the order that
  // does not strand focus: on open it captures the opener, inerts the rest of
  // the app (rail + main behind the scrim), focuses the panel, and traps Tab; on
  // close it un-inerts BEFORE restoring focus to the opener (which lives in the
  // inerted <main>, so restoring before un-inert would be a no-op in WebKit).
  // Escape is handled separately below because it must run in the capture phase
  // to peel one overlay at a time.
  const scrimRef = useModalDialog<HTMLDivElement>(request != null);

  // Announce the host so shared surfaces (SourceInspector) can offer the
  // "Open the document" affordance only where it can actually render.
  useEffect(() => {
    examinationHostMounted.value = true;
    return () => {
      examinationHostMounted.value = false;
    };
  }, []);

  // Resolve the file type from the engine when the caller does not know it
  // (citations carry document_id but not file_type).
  useEffect(() => {
    setResolvedType(null);
    setResolveFailed(false);
    if (!docId || knownType) {
      return;
    }
    let disposed = false;
    void documents
      .detail(docId)
      .then((detail) => {
        if (!disposed) {
          setResolvedType(detail.document.file_type ?? "");
        }
      })
      .catch(() => {
        if (!disposed) {
          setResolveFailed(true);
        }
      });
    return () => {
      disposed = true;
    };
  }, [docId, knownType]);

  // Escape closes THIS layer only. Capture phase + stopImmediatePropagation:
  // the Examination drawer (and the passage overlay) also close on Escape via
  // bubble-phase listeners, so a bubble listener here would collapse the whole
  // stack with one keypress. The capture listener runs first and consumes the
  // key, so Escape peels overlays one layer at a time, the way a lawyer expects
  // a stack of paper to behave. (Tab-trapping and the inert background are
  // handled by the shared hooks above.)
  useEffect(() => {
    if (!request) {
      return undefined;
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopImmediatePropagation();
        closeExamination();
      }
    }
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [request]);

  if (!request) {
    return null;
  }

  const fileType = knownType ?? resolvedType;
  const kind = fileType !== null ? paneKindFor(fileType) : null;
  const locator = request.page ? `p. ${request.page}` : null;

  return (
    <div
      ref={scrimRef}
      className={styles.scrim}
      role="presentation"
      onClick={() => closeExamination()}
    >
      <div
        className={`${verifyStyles.verifyScope} ${styles.panel}`}
        role="dialog"
        aria-modal="true"
        aria-label={`Examining ${request.filename}`}
        onClick={(event) => event.stopPropagation()}
      >
        <header className={styles.panelHead}>
          <div className={styles.panelTitleBlock}>
            <span className={styles.panelTitle}>{request.filename}</span>
            {locator ? <span className={styles.panelLocator}>Cited at {locator}</span> : null}
          </div>
          <button
            type="button"
            className={styles.panelClose}
            onClick={() => closeExamination()}
            aria-label="Close the record"
          >
            Close
          </button>
        </header>
        <div className={styles.panelBody}>
          {kind === "pdf" ? (
            <PdfExamination docId={request.docId} page={request.page} quote={request.quote} />
          ) : kind === "docx" || kind === "txt" ? (
            <DocxExamination docId={request.docId} kind={kind} quote={request.quote} />
          ) : kind === "unsupported" ? (
            <div className={styles.paneMessage}>
              <p className={styles.paneError}>
                This record's file type ({fileType || "unknown"}) cannot be displayed in place.
              </p>
              <p className={styles.paneHint}>
                The verification itself is unaffected; the engine checked the record's extracted
                text.
              </p>
            </div>
          ) : resolveFailed ? (
            <div className={styles.paneMessage}>
              <p className={styles.paneError}>The record's details could not be loaded.</p>
              <p className={styles.paneHint}>Check that the engine is running, then reopen it.</p>
            </div>
          ) : (
            <div className={styles.paneMessage}>
              <Spinner size={16} />
              <span>Opening the record…</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
