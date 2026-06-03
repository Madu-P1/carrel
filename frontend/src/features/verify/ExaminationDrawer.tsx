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
 */
function checksFor(card: VerifyClaimVerdict): CheckRow[] {
  const cases = (card.case_verdicts ?? []).flatMap((b) => (b?.ok ? (b.verdicts ?? []) : []));
  const anyCase = cases[0];
  const caseExists: CheckState = cases.length === 0 ? "unknown" : anyCase?.exists ? "pass" : "flag";
  // Holding match: assistive. True -> query-pass-ish (we still show it as a
  // query, never a confident tick); False -> flag; None/missing -> unknown.
  const holding = anyCase?.holding_match;
  const holdingState: CheckState =
    holding === true ? "query" : holding === false ? "flag" : "unknown";
  const grounded: CheckState = card.verdict === "verified" ? "pass" : card.verdict === "unsupported" ? "flag" : "unknown";

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
          ? "The cited case resolves to a real opinion."
          : caseExists === "flag"
            ? "No case matching this citation was found in the record checked."
            : "No case citation to check."
    },
    {
      name: "Holding matches the claim",
      weight: "Assistive",
      state: holdingState,
      detail:
        holdingState === "flag"
          ? "The cited case is real but may not stand for this claim. For your review."
          : holdingState === "query"
            ? "The cited opinion appears to support this. Confirm against the source."
            : "Not assessed."
    },
    {
      name: "Quotation verbatim",
      weight: "Deterministic",
      state: "unknown",
      detail: "Draft-quote checks appear with the source below."
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

  useEffect(() => {
    if (open) closeRef.current?.focus();
  }, [open, card]);

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
      className={[styles.exam, open ? styles.examOpen : ""].join(" ")}
      role="dialog"
      aria-modal="false"
      aria-label="Examination"
      aria-hidden={!open}
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
