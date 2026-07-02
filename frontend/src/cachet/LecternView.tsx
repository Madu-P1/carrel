import { useEffect, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { VerifyResults } from "@/features/verify/VerifyResults";
import { useVerify } from "@/features/verify/useVerify";
import verifyStyles from "@/features/verify/VerifyView.module.css";

import { CachetMark } from "./CachetMark";
import { openExamination } from "./examine/examineStore";
import { liveDraft } from "./liveDraft";
import { lecternVerify } from "./liveVerify";
import {
  clearSource,
  loadedSource,
  refreshSources,
  setActiveRecord,
  sourceDocs,
  sourceUpload,
  uploadSource
} from "./source";
import styles from "./cachet.module.css";

/**
 * The lectern: a composed title page that IS the verify surface. The mark, one
 * line of what Cachet verifies and refuses, a paste affordance that reads as a
 * sheet of paper, and the record to check against. Verifying runs the check in
 * place — the verdict unfolds directly beneath the sheet on the same page, so
 * there is no second compose form and no hand-off to a separate route. The
 * verdict render is the shared `VerifyResults`, the same one Carrel's VerifyView
 * uses; the engine is the shared `useVerify`.
 *
 * SM-V1 in spirit: the writing area IS the sheet. We do not promise an outcome
 * here; we set up the honest gap the verdict lands in, right below.
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

  // The record to verify against. A user can attach it right here (upload a PDF
  // or Word file) or pick one already filed in Sources; the active record's doc
  // id scopes the check.
  const source = loadedSource.value;
  const upload = sourceUpload.value;
  const docs = sourceDocs.value;
  const [sourceError, setSourceError] = useState<string | null>(null);

  // The module-scope store makes the verdict survive the shell's
  // unmount-on-nav, the same way liveDraft preserves the paste: glance at the
  // Shelf mid-review and the verdict is still here on return (liveVerify.ts).
  const engine = useVerify({
    docIds: source?.docId ? [source.docId] : undefined,
    store: lecternVerify
  });
  // The verdict region replaces the centred title-page layout once a check is in
  // flight or has landed (or errored), so the page scrolls from the top instead
  // of staying vertically centred.
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

  return (
    <section className={styles.lectern} data-active={hasVerdict ? "true" : undefined}>
      <CachetMark size={76} strokeWidth={26} className={styles.lecternMark} />
      <h1 className={styles.wordmark}>Cachet</h1>
      <p className={styles.standing}>The independent attestation layer</p>
      <p className={styles.tagline}>
        Cachet certifies only what it can trace to the record you provide, and says
        so plainly when it cannot. Every ruling becomes a sealed record you can hand
        to anyone.
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
          <kbd className={styles.sheetKbd} title="Command Enter verifies the draft">
            &#8984;&#9166;
          </kbd>
          {engine.loading ? (
            // The escape hatch a persistent store makes necessary: loading
            // survives navigation by design, so a hung stream would otherwise
            // leave Verify disabled forever (the remount no longer resets it).
            <button
              type="button"
              className={styles.lecternSourceChange}
              onClick={() => engine.cancel()}
            >
              Stop the check
            </button>
          ) : null}
          <button
            type="button"
            className={styles.sheetGo}
            onClick={verify}
            disabled={!ready || engine.loading}
          >
            {engine.loading ? "Verifying…" : "Verify"}
          </button>
        </div>
      </div>

      <div className={styles.lecternSource}>
        {source ? (
          <p className={styles.lecternSourceLoaded}>
            <span className={styles.lecternSourceDot} aria-hidden="true" />
            <button
              type="button"
              className={styles.lecternSourceName}
              onClick={() => openExamination({ docId: source.docId, filename: source.filename })}
              aria-label={`Open ${source.filename}`}
              title="Open the record"
            >
              {source.filename}
            </button>
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
          <>
            {docs && docs.length > 0 ? (
              <select
                className={styles.lecternRecordSelect}
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
            <label className={styles.lecternSourceAdd} data-busy={upload ? "true" : undefined}>
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
        {sourceError ? (
          <span className={styles.lecternSourceError}>{sourceError}</span>
        ) : null}
      </div>

      {!ready && !hasVerdict ? (
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

      <dl className={styles.lecternSpine} aria-label="What this machine guarantees">
        <div className={styles.spineItem}>
          <dt className={styles.spineTerm}>On device</dt>
          <dd className={styles.spineGloss}>The substance never leaves this machine.</dd>
        </div>
        <div className={styles.spineItem}>
          <dt className={styles.spineTerm}>Independent</dt>
          <dd className={styles.spineGloss}>It grades the output, never its own.</dd>
        </div>
        <div className={styles.spineItem}>
          <dt className={styles.spineTerm}>Sealed</dt>
          <dd className={styles.spineGloss}>A record you can hand to anyone.</dd>
        </div>
      </dl>

      {hasVerdict ? (
        <div className={[styles.lecternVerdict, verifyStyles.verifyScope].join(" ")}>
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
      ) : null}
    </section>
  );
}
