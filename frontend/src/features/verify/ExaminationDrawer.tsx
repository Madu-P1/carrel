/**
 * Cachet PR5b (Direction A) — the Examination drawer.
 *
 * A slide-in drawer (the one prototype-sanctioned motion beyond the working
 * indicator and the cert seal) that surfaces, for one claim under examination:
 * the claim sentence, the four checks shown SEPARATELY at unequal trust weights
 * (never fused into a single score), and the cited source (re-homed
 * SourceInspectorBody). Showing the four signals apart is the core trust move;
 * a single confidence number is banned.
 *
 * role="dialog" aria-modal="false": the record behind stays a legitimate
 * reading surface (non-modal by design). Focus moves to Close on open and
 * returns to the opener on close; Escape closes.
 */
import { useEffect, useRef } from "preact/hooks";

import { useInert } from "@/design-system";
import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { dispositionForClaim } from "./claimDisposition";
import { SourceInspectorBody } from "./SourceInspector";
import styles from "./VerifyView.module.css";

type CheckState = "pass" | "flag" | "query" | "unknown";

interface CheckRow {
  name: string;
  weight: "Deterministic" | "Assistive";
  state: CheckState;
  detail: string;
}

/**
 * Derive the four checks for a claim from its verdict data. Deterministic checks
 * (case-exists, quote-verbatim) read hard pass/flag; the holding-match is
 * assistive (a query, never a confident verdict color). Good-law is under-
 * claimed: shown as a candidate, not a KeyCite substitute.
 *
 * Register rules, the same ones claimDisposition locks at the claim level:
 *  - judged over ALL cited cases, never cases[0]; one real case must not hide
 *    a second missing one, and a clean first cite must not mute a later flag.
 *  - a bounded-corpus miss is "outside my coverage" (unknown), never the flag
 *    accusation; the offline corpus cannot tell fabricated from unbundled.
 *  - a holding contradiction is an AI judgment and wears the query register,
 *    never the deterministic flag.
 *
 * Exported for direct unit testing (ExaminationDrawer.test.tsx).
 */
export function checksFor(card: VerifyClaimVerdict): CheckRow[] {
  type CaseRead = {
    exists?: boolean;
    status?: number;
    holding_match?: boolean | null;
    bounded_corpus?: boolean;
    caption_mismatch?: boolean;
  };
  const cases = (card.case_verdicts ?? []).flatMap((b) =>
    b?.ok ? ((b.verdicts ?? []) as CaseRead[]) : []
  );
  const anyCaptionMismatch = cases.some((c) => Boolean(c.caption_mismatch));
  const anyNationalMiss = cases.some(
    (c) => !c.exists && !c.bounded_corpus && (c.status === 404 || c.status === 400)
  );
  const anyBoundedMiss = cases.some(
    (c) => !c.exists && Boolean(c.bounded_corpus) && (c.status === 404 || c.status === 400)
  );
  const allExist = cases.length > 0 && cases.every((c) => Boolean(c.exists));
  const caseExists: CheckState =
    cases.length === 0
      ? "unknown"
      : anyCaptionMismatch || anyNationalMiss
        ? "flag"
        : allExist
          ? "pass"
          : "unknown";
  // Holding match: assistive. Any signal (support or contradiction) is a query
  // for the lawyer's review — never a confident tick, never the oxblood flag.
  const anyContradiction = cases.some((c) => c.holding_match === false);
  const anySupport = cases.some((c) => c.holding_match === true);
  const holdingState: CheckState = anyContradiction || anySupport ? "query" : "unknown";
  // "Grounded in your sources" reflects ONLY loaded-source (contract) grounding.
  // A citation claim is judged by "Cited case exists" instead, and the litigator
  // cite-check loads no sources, so deriving this from the top-line verdict would
  // flag "nothing supports this" when there is nothing to support against. A
  // citation claim therefore reads N/A here, never a red contradiction.
  const grounded: CheckState =
    cases.length > 0
      ? "unknown"
      : card.verdict === "verified"
        ? "pass"
        : card.verdict === "unsupported"
          ? "flag"
          : "unknown";

  return [
    {
      name: "Grounded in your sources",
      weight: "Deterministic",
      state: grounded,
      detail:
        grounded === "pass"
          ? "A loaded source supports this statement."
          : grounded === "flag"
            ? "Nothing in the loaded sources supports this statement."
            : "Not checked against loaded sources."
    },
    {
      name: "Cited case exists",
      weight: "Deterministic",
      state: caseExists,
      detail:
        caseExists === "pass"
          ? cases.length > 1
            ? "Every cited case resolves to a real opinion."
            : "The cited case resolves to a real opinion."
          : caseExists === "flag"
            ? anyCaptionMismatch
              ? "A citation resolves to a different case than the one named in the draft."
              : "No case matching this citation was found in the record checked."
            : cases.length === 0
              ? "No case citation to check."
              : anyBoundedMiss
                ? "A citation is outside the offline corpus checked. Confirm it against the full national database."
                : "A citation could not be checked."
    },
    {
      name: "Holding matches the claim",
      weight: "Assistive",
      state: holdingState,
      detail: anyContradiction
        ? "The cited case is real but may not stand for this claim. For your review."
        : anySupport
          ? "The cited opinion appears to support this. Confirm against the source."
          : "Not assessed."
    },
    {
      name: "Quotation verbatim",
      weight: "Deterministic",
      state: "unknown",
      // True whether or not a source section renders below; the old wording
      // promised content "below" that a no-source claim never shows.
      detail: "Draft-quote checks appear alongside the source when one is attached."
    }
  ];
}

interface ExaminationDrawerProps {
  card: VerifyClaimVerdict | null;
  open: boolean;
  onClose: () => void;
}

export function ExaminationDrawer({ card, open, onClose }: ExaminationDrawerProps) {
  const closeRef = useRef<HTMLButtonElement | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);
  // The drawer stays mounted and slides; while closed it must be inert so its
  // Close button (and the source links inside) are not tabbable controls
  // stranded in an aria-hidden subtree (WCAG 4.1.2). aria-modal stays false:
  // the record behind is a legitimate reading surface, so Tab is NOT trapped.
  const asideRef = useInert<HTMLElement>(!open);

  // Capture the opener when the drawer opens and return focus to it on close,
  // the contract this component's docstring promises. Keyed on `open` only:
  // re-capturing on a claim switch (card change) while open would overwrite the
  // opener with the Close button and break the restore.
  useEffect(() => {
    if (open) {
      openerRef.current = document.activeElement as HTMLElement | null;
      closeRef.current?.focus();
    } else if (openerRef.current) {
      openerRef.current.focus?.();
      openerRef.current = null;
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  const checks = card ? checksFor(card) : [];
  const disposition = card ? dispositionForClaim(card) : null;

  return (
    <aside
      ref={asideRef}
      className={[styles.exam, open ? styles.examOpen : ""].join(" ")}
      role="dialog"
      aria-modal="false"
      aria-label="Examination"
    >
      <header className={styles.examHead}>
        <span className={styles.examLabel}>Examination</span>
        <button type="button" className={styles.examClose} onClick={onClose} ref={closeRef}>
          Close
        </button>
      </header>
      {card ? (
        <div className={styles.examBody}>
          <p className={styles.examClaim}>{card.claim_text}</p>
          <section className={styles.checks} aria-label="The four checks">
            <h3 className={styles.checksLabel}>Four checks, shown separately</h3>
            {checks.map((ck) => (
              <div key={ck.name} className={styles.check} data-state={ck.state}>
                <span className={styles.checkMark} aria-hidden="true" />
                <div>
                  <span className={styles.checkName}>
                    {ck.name}
                    <span className={styles.checkWeight}>{ck.weight}</span>
                  </span>
                  <p className={styles.checkDetail}>{ck.detail}</p>
                </div>
              </div>
            ))}
          </section>
          {disposition ? <SourceInspectorBody card={card} disposition={disposition} /> : null}
        </div>
      ) : null}
    </aside>
  );
}
