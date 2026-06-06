import { useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { CachetMark } from "@/design-system";

import { liveDraft } from "./liveDraft";
import { stashPendingDraft } from "./pendingDraft";
import { clearSource, loadedSource, sourceUpload, uploadSource } from "./source";
import styles from "./cachet.module.css";

/**
 * The lectern: a composed title page. The mark, one line of what Cachet
 * verifies and refuses, and a paste affordance that reads as a sheet of paper,
 * not an input box. The paste is the lever (Loop 1): on Verify we stash the
 * draft and hand off to the verify view, which runs the check on mount.
 *
 * SM-V1 in spirit: the writing area IS the sheet. We do not promise an outcome
 * here; we set up the honest gap the verdict will land in.
 */
export function LecternView() {
  // The draft lives in the shared `liveDraft` signal, not local state, so a paste
  // on the home page survives navigating to the Shelf and back (the route swap
  // unmounts this view) and flows into the verify station unchanged.
  const draft = liveDraft.value;
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const ready = draft.trim().length > 0;

  // The record to verify against. A user can attach it right here (upload a PDF
  // or Word file) instead of going to the Sources tab; the loaded source flows
  // into the verify check (CachetApp passes its doc id as docIds).
  const source = loadedSource.value;
  const upload = sourceUpload.value;
  const [sourceError, setSourceError] = useState<string | null>(null);

  async function onSourceFile(files: FileList | null | undefined) {
    const file = files && files[0];
    if (!file || upload) return;
    setSourceError(null);
    try {
      await uploadSource(file);
    } catch (e) {
      setSourceError(e instanceof Error ? e.message : "The record could not be loaded.");
    }
  }

  function verify() {
    if (!ready) {
      areaRef.current?.focus();
      return;
    }
    stashPendingDraft(draft);
    navigateTo("/verify");
  }

  function onKeyDown(event: preact.JSX.TargetedKeyboardEvent<HTMLTextAreaElement>) {
    // Keyboard-first: Cmd/Ctrl + Enter verifies from the sheet.
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      verify();
    }
  }

  return (
    <section className={styles.lectern}>
      <CachetMark size={76} className={styles.lecternMark} />
      <h1 className={styles.wordmark}>Cachet</h1>
      <p className={styles.tagline}>
        Independent verification for high-stakes drafts. Cachet certifies only what
        it can trace to the record, and says so plainly when it cannot.
      </p>

      <div className={styles.sheet}>
        <textarea
          ref={areaRef}
          className={styles.sheetArea}
          value={draft}
          placeholder="Paste a draft to verify"
          aria-label="Draft to verify"
          spellcheck={false}
          onInput={(e) => (liveDraft.value = (e.target as HTMLTextAreaElement).value)}
          onKeyDown={onKeyDown}
        />
        <div className={styles.sheetFoot}>
          <span className={styles.sheetHint}>
            Reads the citations and quotes against the sources you provide
          </span>
          <button
            type="button"
            className={styles.sheetGo}
            onClick={verify}
            disabled={!ready}
          >
            Verify
          </button>
        </div>
      </div>

      <div className={styles.lecternSource}>
        {source ? (
          <p className={styles.lecternSourceLoaded}>
            <span className={styles.lecternSourceDot} aria-hidden="true" />
            <span className={styles.lecternSourceName}>{source.filename}</span>
            <span className={styles.lecternSourceTag}>loaded as the record</span>
            <button
              type="button"
              className={styles.lecternSourceChange}
              onClick={() => clearSource()}
            >
              change
            </button>
          </p>
        ) : (
          <label className={styles.lecternSourceAdd} data-busy={upload ? "true" : undefined}>
            <input
              type="file"
              accept=".pdf,.docx,.txt"
              className={styles.dropzoneInput}
              disabled={!!upload}
              onChange={(e) => void onSourceFile((e.target as HTMLInputElement).files)}
            />
            {upload
              ? `Reading ${upload.filename}${upload.fraction < 1 ? ` ${Math.round(upload.fraction * 100)}%` : "…"}`
              : "Add the record to check against: a contract, PDF, or Word file"}
          </label>
        )}
        {sourceError ? (
          <span className={styles.lecternSourceError}>{sourceError}</span>
        ) : null}
      </div>

      <p className={styles.lecternMeta}>Nothing leaves this machine without your say</p>
    </section>
  );
}
