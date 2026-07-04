import { useEffect, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { ErrorBoundary } from "@/design-system";
import { VerifyResults } from "@/features/verify/VerifyResults";
import { useVerify } from "@/features/verify/useVerify";
import verifyStyles from "@/features/verify/VerifyView.module.css";

import { openExamination } from "./examine/examineStore";
import { resetVerifyStore } from "@/features/verify/useVerify";

import { liveDraft } from "./liveDraft";
import { lecternVerify } from "./liveVerify";
import {
  clearSource,
  loadedSource,
  refreshSources,
  setActiveRecord,
  sourceDocs,
  sourcesError,
  sourceUpload,
  uploadSource
} from "./source";
import styles from "./cachet.module.css";

/**
 * The Lectern composer (handoff §3): a centered 760px column — the "Checking
 * against" pill row, a large serif sheet (Newsreader 18.5/1.75), and the
 * primary Verify draft action with its ⌘↩ chord. The composer IS the landing
 * surface; the brand lives in the splash and the top strip, not in a hero.
 * Verifying unfolds the verdict in place beneath (Flow A) — no second compose
 * form, no route hand-off. The verdict render is the shared `VerifyResults`;
 * the engine is the shared `useVerify`.
 */

/* The specimen: a litigator-shaped draft with planted defects, so a cold
 * lectern can be examined in one click instead of opening on a blank void.
 * Stated plainly as a specimen; the flaws are the point (the refusal and the
 * flag are what the surface exists to show). Three physical lines so the
 * sentence splitter reads three statements. */
const SPECIMEN_DRAFT =
  'The Supreme Court held that "separate educational facilities are inherently unequal." Brown v. Board of Education, 347 U.S. 483 (1954).\n' +
  "The settlement fund totals $360 million, payable to the class within 30 days of final approval.\n" +
  "That outcome was reaffirmed in Vandelay Industries v. Kramer, 512 U.S. 901 (1994).";

export function LecternView() {
  // The draft lives in the shared `liveDraft` signal, not local state, so a paste
  // on the home page survives navigating to the Shelf and back (the route swap
  // unmounts this view) and is unchanged when the view remounts.
  const draft = liveDraft.value;
  const areaRef = useRef<HTMLTextAreaElement | null>(null);
  const ready = draft.trim().length > 0;
  const wordCount = draft.trim().split(/\s+/).filter(Boolean).length;

  // The record to verify against. A user can attach it right here (upload a PDF
  // or Word file) or pick one already filed in Sources; the active record's doc
  // id scopes the check.
  const source = loadedSource.value;
  const upload = sourceUpload.value;
  const docs = sourceDocs.value;
  // Non-blocking load error for the record library (refreshSources' fetch):
  // surfaced here so a failed library fetch on the primary landing surface is
  // never silent — the dropzone still works even while this is shown.
  const docsError = sourcesError.value;
  const [sourceError, setSourceError] = useState<string | null>(null);

  // The module-scope store makes the verdict survive the shell's
  // unmount-on-nav, the same way liveDraft preserves the paste: glance at the
  // Shelf mid-review and the verdict is still here on return (liveVerify.ts).
  const engine = useVerify({
    docIds: source?.docId ? [source.docId] : undefined,
    store: lecternVerify
  });
  // The verdict region takes over once a check is in flight or has landed (or
  // errored): the composer yields the page to the run view (handoff §4 —
  // showComposer only while idle).
  const hasVerdict = engine.loading || engine.response !== null || engine.error !== null;

  // Populate the record list so the "pick a loaded record" control is available
  // even on a cold lectern (the user came straight here without visiting Sources).
  useEffect(() => {
    void refreshSources();
  }, []);

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
    void engine.verify(draft);
  }

  // SM-V7 command spine: the ⌘K palette dispatches `cachet:command` and
  // dismisses itself; the lectern owns the draft, so the verify verb lands
  // here. The ref keeps the listener registered once while always invoking the
  // current closure (draft and engine change every render).
  const verifyRef = useRef(verify);
  verifyRef.current = verify;
  useEffect(() => {
    function onCommand(event: Event) {
      const id = (event as CustomEvent<{ id?: string }>).detail?.id;
      if (id === "verify-draft") verifyRef.current();
    }
    window.addEventListener("cachet:command", onCommand);
    return () => window.removeEventListener("cachet:command", onCommand);
  }, []);

  function onKeyDown(event: preact.JSX.TargetedKeyboardEvent<HTMLTextAreaElement>) {
    // Keyboard-first: Cmd/Ctrl + Enter verifies from the sheet.
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      verify();
    }
  }

  const composer = (
    <div className={styles.composer}>
      <div className={styles.pillRow}>
        <span className={styles.pillLabel}>Checking against</span>
        {source ? (
          <span className={styles.pill}>
            <button
              type="button"
              className={styles.pillName}
              onClick={() => openExamination({ docId: source.docId, filename: source.filename })}
              aria-label={`Open ${source.filename}`}
              title="Open the record"
            >
              {source.filename}
            </button>
            <button
              type="button"
              className={styles.pillChange}
              onClick={() => clearSource()}
              aria-label="Change the record"
            >
              change
            </button>
          </span>
        ) : (
          <>
            {docs && docs.length > 0 ? (
              <select
                className={styles.pillSelect}
                aria-label="Check against a loaded record"
                value=""
                onChange={(e) => {
                  const id = (e.target as HTMLSelectElement).value;
                  const doc = docs.find((d) => d.id === id);
                  if (doc) setActiveRecord(doc);
                }}
              >
                <option value="">Check against a loaded record…</option>
                {docs.map((d) => (
                  <option key={d.id} value={d.id}>
                    {d.filename}
                  </option>
                ))}
              </select>
            ) : null}
            <label
              className={`${styles.pill} ${styles.pillUpload}`}
              data-busy={upload ? "true" : undefined}
            >
              <input
                type="file"
                accept=".pdf,.docx,.txt,.md"
                className={styles.dropzoneInput}
                disabled={!!upload}
                onChange={(e) => void onSourceFile((e.target as HTMLInputElement).files)}
              />
              {upload
                ? `Reading ${upload.filename}${upload.fraction < 1 ? ` ${Math.round(upload.fraction * 100)}%` : "…"}`
                : "Add the record to check against: a contract, PDF, or Word file"}
            </label>
          </>
        )}
        <span className={styles.pillQuiet}>Case-law store · bundled</span>
      </div>

      <textarea
        ref={areaRef}
        className={styles.composerArea}
        value={draft}
        placeholder="Paste the draft to check."
        aria-label="Draft to verify"
        spellcheck={false}
        onInput={(e) => (liveDraft.value = (e.target as HTMLTextAreaElement).value)}
        onKeyDown={onKeyDown}
      />

      <div className={styles.composerFoot}>
        <button
          type="button"
          className={styles.verifyDraftBtn}
          onClick={verify}
          disabled={!ready || engine.loading}
        >
          {engine.loading ? "Verifying…" : "Verify draft"}
          <kbd className={styles.kbdChip} title="Command Enter verifies the draft">
            &#8984;&#9166;
          </kbd>
        </button>
        <span className={styles.wordHelper}>{wordCount} words · reads only, never rewrites</span>
      </div>

      {docsError ? (
        <span className={styles.lecternSourceError} role="alert">
          {docsError}
        </span>
      ) : null}
      {sourceError ? <span className={styles.lecternSourceError}>{sourceError}</span> : null}

      {!ready ? (
        // The cold lectern's one-click first move: a specimen with planted
        // defects, so the first thing a skeptic sees is the surface refusing
        // and flagging, not a blank void asking for trust up front.
        <button
          type="button"
          className={styles.lecternSpecimen}
          onClick={() => {
            liveDraft.value = SPECIMEN_DRAFT;
            areaRef.current?.focus();
          }}
        >
          Or examine a specimen draft with planted defects
        </button>
      ) : null}
    </div>
  );

  return (
    <section className={styles.lectern} data-active={hasVerdict ? "true" : undefined}>
      {hasVerdict ? (
        // A malformed/unexpected wire shape (missing or mistyped fields) must
        // not blank the whole lectern — a reset back to the composer stays
        // reachable even if the verdict tree itself can't render. Keyed on
        // engine.response so a fresh verify (which nulls it, then sets a new
        // object) always clears a prior crash.
        <ErrorBoundary
          resetKey={engine.response}
          fallback={() => (
            <div className={[styles.lecternVerdict, verifyStyles.verifyScope].join(" ")}>
              <p className={styles.lecternSourceError} role="alert">
                The verification result could not be displayed. Nothing here has been verified —
                verify the draft again.
              </p>
              {/* The composer yields to the run view, so a crashed verdict must
                  hand back an explicit way home or the surface is stranded. */}
              <button
                type="button"
                className={styles.stopCheck}
                onClick={() => resetVerifyStore(lecternVerify)}
              >
                New draft
              </button>
            </div>
          )}
        >
          <div className={[styles.lecternVerdict, verifyStyles.verifyScope].join(" ")}>
            {engine.loading ? (
              // The escape hatch a persistent store makes necessary: loading
              // survives navigation by design, so a hung stream would otherwise
              // leave Verify disabled forever (the remount no longer resets it).
              // Cancelling settles to idle, which returns the composer.
              <button
                type="button"
                className={styles.stopCheck}
                onClick={() => engine.cancel()}
              >
                Stop the check
              </button>
            ) : null}
            <VerifyResults
              engine={engine}
              draft={draft}
              // The refusal CTA says "could not be checked without the records
              // they rely on" — true only when nothing is attached. With a
              // record loaded and consulted (a conflict refusal, a value the
              // record lacks), pointing at the Vault would overclaim the cause,
              // so the CTA is withheld.
              onResolve={source ? undefined : () => navigateTo("/vault")}
            />
          </div>
        </ErrorBoundary>
      ) : (
        composer
      )}
    </section>
  );
}
