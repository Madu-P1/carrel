import { useEffect, useRef, useState } from "preact/hooks";

import { Button } from "@/design-system";

import { CachetMark } from "@/cachet/CachetMark";

import { certificationToJson, sealStateFor, type CertificationModel } from "./certification";
import { tierForKind } from "./claimDisposition";
import styles from "./VerifyView.module.css";

/** Download the machine-readable certification alongside the print-to-PDF exhibit. */
function downloadCertificationJson(model: CertificationModel): void {
  const blob = new Blob([certificationToJson(model)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `cachet-certification-${model.fingerprint.slice(0, 8)}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function formatStamp(iso: string): string {
  return iso
    .replace("T", " ")
    .replace(/\.\d+Z$/, " UTC")
    .replace(/Z$/, " UTC");
}

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

interface CertificationExhibitProps {
  model: CertificationModel;
  onClose: () => void;
  /**
   * Cachet PR6d: called when the human SEALS (clicks Set the seal). The Verify
   * view uses this to persist the brief to the Shelf as Sealed (seal == save).
   * Optional, so a standalone/preview render works without it.
   */
  onSeal?: () => void;
  /**
   * The seal fingerprint to initialize from: a reopened saved brief's stored
   * seal, or a LIVE seal recorded on the engine via markSealed (the lectern's
   * persistent store carries it across remounts). When it matches the seal
   * shows "sealed"; when the draft has since changed it shows "cracked". Omit
   * when nothing is sealed (the seal starts unsealed, set by a click). Only
   * "unsealed"/"sealed" are ever persisted, so this is a bare fingerprint
   * string, not a SealState; cracked is always derived here, never stored.
   */
  sealedFingerprint?: string | null;
  /**
   * Fingerprint of the draft AS IT IS NOW on the host's composer, when the
   * host can know it. The cracked register compares the seal against this, so
   * a seal set on text that has since been edited reads cracked on the live
   * flow too, not only on a reopened brief. Defaults to the model's own
   * checked-text fingerprint (the pre-existing behavior).
   */
  currentFingerprint?: string;
}

/**
 * The exportable certification: a dated, fingerprinted, court-exhibit-shaped
 * record. Exported via the OS print dialog (Save as PDF), so it needs no PDF
 * dependency. The "items requiring attorney review" section leads; the human is
 * kept in the chair (the tool checks, the attorney certifies). No confidence
 * numbers, by design.
 */
export function CertificationExhibit({
  model,
  onClose,
  onSeal,
  sealedFingerprint: persistedSealedFingerprint,
  currentFingerprint
}: CertificationExhibitProps) {
  const stamp = formatStamp(model.generatedAtISO);
  const dialogRef = useRef<HTMLDivElement>(null);
  // Keep the effect's deps empty while always invoking the latest onClose, so a
  // parent re-render while the exhibit is open cannot re-run the effect and
  // re-steal focus or re-capture the restore target.
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  // Modal keyboard a11y: focus enters the exhibit on open, Tab is trapped
  // while it is open, Escape closes it, and focus returns to the trigger on
  // close. A litigator must be able to dismiss their exhibit without a pointer.
  useEffect(() => {
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const root = dialogRef.current;
    const focusable = () =>
      root
        ? Array.from(
            root.querySelectorAll<HTMLElement>(
              'a[href], button:not([disabled]), [tabindex]:not([tabindex="-1"])'
            )
          )
        : [];
    (focusable()[0] ?? root)?.focus();
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key === "Tab") {
        const items = focusable();
        if (items.length === 0) return;
        const firstEl = items[0];
        const lastEl = items[items.length - 1];
        if (event.shiftKey && document.activeElement === firstEl) {
          event.preventDefault();
          lastEl.focus();
        } else if (!event.shiftKey && document.activeElement === lastEl) {
          event.preventDefault();
          firstEl.focus();
        }
      }
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
      previouslyFocused?.focus?.();
    };
  }, []);

  // The seal: the human attests by clicking, capturing the draft fingerprint at
  // seal-time. A later draft whose fingerprint no longer matches reads "cracked"
  // (a quiet dimmed re-verify nudge, never an oxblood flag). Within one open
  // exhibit the model is fixed, so only unsealed -> sealed happens here; the
  // cracked state is reached when a persisted seal is reopened against a changed
  // draft (Shelf persistence, PR6). Pure logic lives in sealStateFor.
  // Seed once from a persisted seal (a reopened saved brief); null for the live
  // verify flow. Seed-once is safe because the exhibit mounts fresh on each cert
  // open (certModel toggles null between opens) AND VerifyView is keyed on briefId
  // in App.tsx, so switching briefs remounts the whole subtree and re-reads this
  // seed. Do NOT reseed on prop change, which would clobber a live unsealed ->
  // sealed click within one open exhibit.
  const [sealedFingerprint, setSealedFingerprint] = useState<string | null>(
    () => persistedSealedFingerprint ?? null
  );
  const sealRef = useRef<HTMLDivElement>(null);
  const pressRef = useRef<HTMLSpanElement>(null);
  const crackPathRef = useRef<SVGPathElement>(null);
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const sealState = sealStateFor(sealedFingerprint, currentFingerprint ?? model.fingerprint);
  const sealAriaLabel =
    sealState === "sealed"
      ? "Certification seal, set"
      : sealState === "cracked"
        ? "Certification seal cracked: the draft changed since it was sealed"
        : "Certification seal, not yet set";

  const handleSetSeal = () => {
    setSealedFingerprint(model.fingerprint);
    // seal == save: persist this brief to the Shelf as Sealed (PR6d). The Verify
    // view's onSeal handler does the save; safe to call with the local seal set.
    onSeal?.();
    // The seal button disables once set, so move focus to a stable in-dialog
    // control; otherwise the browser drops focus to <body>, escaping the trap.
    closeButtonRef.current?.focus();
    if (prefersReducedMotion()) return;
    sealRef.current?.animate(
      [
        { transform: "translateY(-6px) scale(1.06)", opacity: 0.6 },
        { transform: "translateY(0) scale(0.95)", offset: 0.55 },
        { transform: "translateY(0) scale(1)" }
      ],
      { duration: 900, easing: "cubic-bezier(0.34, 0, 0.2, 1)" }
    );
    pressRef.current?.animate(
      [
        { transform: "scale(0.82)", opacity: 0.55 },
        { transform: "scale(1.85)", opacity: 0 }
      ],
      { duration: 900, delay: 60, easing: "cubic-bezier(0.34, 0, 0.2, 1)" }
    );
  };

  // Draw the crack when the seal goes stale. The dimmed "loss of luster" is the
  // static .sealCracked filter (CSS-transitioned), so the resting state is always
  // class-derived: reduced motion and any later un-crack settle correctly without
  // a forwards-filling WAAPI filter that could strand the seal dimmed.
  useEffect(() => {
    if (sealState !== "cracked" || prefersReducedMotion()) return;
    const path = crackPathRef.current;
    if (!path) return;
    // The crack glyph is ~110 user units long; a fixed dash over-covers it so
    // the stroke draws in from hidden. Avoids getTotalLength (unimplemented in
    // jsdom) so the component test needs no SVG-geometry shim.
    const crackLength = 130;
    path.style.strokeDasharray = String(crackLength);
    path.animate([{ strokeDashoffset: String(crackLength) }, { strokeDashoffset: "0" }], {
      duration: 600,
      easing: "cubic-bezier(0.4, 0, 1, 1)",
      fill: "forwards"
    });
  }, [sealState]);

  return (
    <div
      ref={dialogRef}
      className={styles.certOverlay}
      role="dialog"
      aria-modal="true"
      aria-label="Verification certification"
      tabIndex={-1}
    >
      <div className={styles.certToolbar}>
        <button
          type="button"
          ref={closeButtonRef}
          className={styles.inspectorClose}
          onClick={onClose}
        >
          Close
        </button>
        <Button type="button" variant="ghost" onClick={() => window.print()}>
          Save as PDF
        </Button>
        <Button type="button" variant="ghost" onClick={() => downloadCertificationJson(model)}>
          Save as JSON
        </Button>
      </div>

      <article className={[styles.verifyScope, styles.certExhibit].join(" ")}>
        <div className={styles.exhibitHead}>
          <CachetMark size={34} className={styles.exhibitMark} title="" />
          <div className={styles.exhibitTitle}>CERTIFICATION EXHIBIT</div>
          <div className={styles.exhibitCertNo}>
            {model.fingerprint.slice(0, 12)} · issued {stamp}
          </div>
        </div>
        <div className={styles.cover}>
          <p className={styles.coverKicker}>Certification</p>
          <h2 className={styles.coverTitle}>The record of what was checked</h2>
          <div className={styles.coverBody}>
            <p className={styles.attest}>
              I have reviewed the items flagged below and certify that I exercised diligence in
              verifying the citations in this document against the sources loaded into Cachet on the
              date shown.{" "}
              <strong>
                This certificate attests to grounding, not to the truth or legal soundness of any
                proposition.
              </strong>
            </p>
            <div className={styles.sealZone}>
              <button
                type="button"
                className={styles.btnSeal}
                onClick={handleSetSeal}
                disabled={sealState === "sealed"}
              >
                {sealState === "sealed" ? "Sealed" : "Set the seal"}
              </button>
              <div
                ref={sealRef}
                className={[
                  styles.seal,
                  sealState === "sealed" ? styles.sealSet : "",
                  sealState === "cracked" ? styles.sealCracked : ""
                ].join(" ")}
                role="img"
                aria-label={sealAriaLabel}
              >
                <span ref={pressRef} className={styles.sealPress} aria-hidden="true" />
                <span className={styles.sealMark}>
                  CACHET
                  <br />
                  VERIFIED
                  <br />
                  RECORD
                </span>
                <svg className={styles.crack} viewBox="0 0 104 104" aria-hidden="true">
                  <path
                    ref={crackPathRef}
                    d="M52 4 L46 34 L60 50 L44 66 L56 100"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth={3.2}
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
              {/* Always-present polite live region: when the human sets or the
                  seal cracks, the status text is announced to assistive tech
                  (WCAG 4.1.3), since focus moves to Close and the seal itself is
                  a non-live role=img. Empty (silent) while unsealed. */}
              <span
                className={[
                  styles.sealCaption,
                  sealState === "cracked" ? styles.stale : ""
                ].join(" ")}
                role="status"
                aria-live="polite"
              >
                {sealState === "sealed"
                  ? `Sealed ${stamp}`
                  : sealState === "cracked"
                    ? "Draft changed since sealing, re-verify"
                    : ""}
              </span>
            </div>
          </div>
        </div>

        <div className={styles.coverSeam}>
          <span className={styles.coverSeamLabel}>The record</span>
          <span className={styles.coverSeamRule} />
        </div>

        <header className={styles.certHead}>
          <dl className={styles.certMeta}>
            <div>
              <dt>Generated</dt>
              <dd>{stamp}</dd>
            </div>
            <div>
              <dt>Document fingerprint</dt>
              <dd className={styles.certMono}>{model.fingerprint}</dd>
            </div>
            <div>
              <dt>Statements checked</dt>
              <dd className={styles.certMono}>
                {model.coverage
                  ? `${model.coverage.treated} of ${model.coverage.statements}`
                  : model.totalStatements}
              </dd>
            </div>
            {model.coverage && model.coverage.untreated > 0 ? (
              <div>
                <dt>Not independently checked</dt>
                <dd>
                  {model.coverage.untreated === 1
                    ? "1 statement carried no checkable anchor (such as a citation, quotation, amount, or date) and was not independently checked."
                    : `${model.coverage.untreated} statements carried no checkable anchor (such as a citation, quotation, amount, or date) and were not independently checked.`}
                </dd>
              </div>
            ) : null}
            {model.provider ? (
              <div>
                <dt>Checked by</dt>
                <dd>
                  {model.provider}
                  {model.localExecution ? " (on device)" : " (cloud)"}
                </dd>
              </div>
            ) : null}
            <div>
              <dt>Data handling</dt>
              <dd>{model.attestation}</dd>
            </div>
          </dl>
        </header>

        <section className={styles.certSection}>
          <h3 className={styles.certSectionLabel}>Items requiring attorney review</h3>
          {model.flagged.length === 0 ? (
            <p className={styles.certMuted}>
              {model.coverage && model.coverage.untreated > 0
                ? "No checked statement was flagged. Statements with no checkable anchor were not independently checked. This confirms grounding, not legal correctness."
                : "No items were flagged. Every statement was grounded in the sources provided. This confirms grounding, not legal correctness."}
            </p>
          ) : (
            <ol className={styles.certList}>
              {model.flagged.map((it) => (
                <li key={it.index} className={styles.certItem}>
                  <span className={styles.certItemLabel} data-tier={tierForKind(it.kind)}>
                    {it.label}
                  </span>
                  <span className={styles.certItemClaim}>{it.claimText}</span>
                  {it.sources.length > 0 ? (
                    <span className={styles.certItemSources}>{it.sources.join("; ")}</span>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className={styles.certSection}>
          <h3 className={styles.certSectionLabel}>Complete record of all statements checked</h3>
          <p className={styles.certMuted}>
            The full record, including the items flagged for review above.
          </p>
          <ol className={styles.certList}>
            {model.allItems.map((it) => (
              <li key={it.index} className={styles.certItem}>
                <span className={styles.certItemLabel} data-tier={tierForKind(it.kind)}>
                  {it.label}
                </span>
                <span className={styles.certItemClaim}>{it.claimText}</span>
                {it.sources.length > 0 ? (
                  <span className={styles.certItemSources}>{it.sources.join("; ")}</span>
                ) : null}
              </li>
            ))}
          </ol>
        </section>

        <footer className={styles.certFooter}>
          <p>
            This report records an automated check of the statements above against the sources
            provided, as of {stamp}. It confirms grounding against those sources only. It does not
            assess legal correctness, strategy, or completeness.
          </p>
          <p className={styles.certSign}>
            Reviewed by ______________________. The reviewing attorney is responsible for the
            filing; this report did not draft or approve it.
          </p>
        </footer>
      </article>
    </div>
  );
}
