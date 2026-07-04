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

import { Spinner, useInert } from "@/design-system";
import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { dispositionForClaim, type ClaimDisposition } from "./claimDisposition";
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

  // The engine's own per-claim reason is the honest, specific finding (e.g. "The
  // summary states 60 billion; the loaded source states 20 billion"). Prefer it
  // over the blanket strings so a contradiction reads as the contradiction it is,
  // not "nothing supports this statement" — which is flatly wrong for a sentence
  // that is verbatim except one altered figure. Falls back to the generic copy
  // only when the engine attached no reason.
  const reason = (card.unsupported_reason ?? "").trim() || null;
  const groundedDetail =
    grounded === "pass"
      ? reason ?? "A loaded source supports this statement."
      : grounded === "flag"
        ? reason ?? "The loaded sources do not support this statement as written."
        : "Not checked against loaded sources.";

  return [
    {
      name: "Grounded in your sources",
      weight: "Deterministic",
      state: grounded,
      detail: groundedDetail
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

/** One cited case's register line (re-homed from the retired live card
 *  sub-lines): a bounded-corpus miss is a coverage statement, never the
 *  accusatory "Case not found" the engine refused to assert; a caption
 *  mismatch is the flag by name, never a quiet "Case found" naming the wrong
 *  case. Exported so the register stays unit-locked. */
export function caseLineRegister(verdict: {
  exists?: boolean;
  status?: number;
  bounded_corpus?: boolean;
  caption_mismatch?: boolean;
}): { label: string; kind: "pass" | "flag" | "query" | "unknown" } {
  const captionMismatch = Boolean(verdict.caption_mismatch);
  const boundedMiss =
    !verdict.exists &&
    Boolean(verdict.bounded_corpus) &&
    (verdict.status === 404 || verdict.status === 400) &&
    !captionMismatch;
  if (captionMismatch) return { label: "Resolves to a different case", kind: "flag" };
  if (boundedMiss) return { label: "Outside the offline corpus checked", kind: "unknown" };
  if (verdict.exists) return { label: "Case found", kind: "pass" };
  if (verdict.status === 300) return { label: "Ambiguous (multiple matches)", kind: "query" };
  if (verdict.status === 404) return { label: "Case not found", kind: "flag" };
  if (verdict.status === 400) return { label: "Malformed citation", kind: "flag" };
  return { label: "Verification error", kind: "unknown" };
}

/**
 * Every non-happy path the drawer body can be in, collapsed into one
 * discriminated union so the render side is an exhaustive switch instead of
 * independent booleans that can drift out of sync. "malformed" is reached
 * when checksFor/dispositionForClaim throw on a card whose shape doesn't
 * match what they assume (a truncated stream, a version-skewed payload) —
 * caught here so a bad property access downstream never blanks or crashes
 * the whole verify view.
 *
 * Exported for direct unit testing (ExaminationDrawer.test.tsx), same
 * rationale as checksFor above.
 */
export type ExamState =
  | { kind: "loading" }
  | { kind: "load-error"; message: string }
  | { kind: "empty" }
  | { kind: "malformed" }
  | { kind: "ready"; card: VerifyClaimVerdict; checks: CheckRow[]; disposition: ClaimDisposition };

export function deriveExamState(
  card: VerifyClaimVerdict | null,
  loading: boolean,
  loadError: string | null
): ExamState {
  if (loading) return { kind: "loading" };
  if (loadError) return { kind: "load-error", message: loadError };
  if (!card) return { kind: "empty" };
  try {
    return { kind: "ready", card, checks: checksFor(card), disposition: dispositionForClaim(card) };
  } catch {
    return { kind: "malformed" };
  }
}

const CHECK_GLYPH: Record<string, string> = {
  pass: "\u2713",
  flag: "\u2715",
  query: "\u25C7",
  unknown: "\u2298"
};

interface ExaminationDrawerProps {
  card: VerifyClaimVerdict | null;
  open: boolean;
  onClose: () => void;
  /** True while the source document behind this claim is still being
   * fetched. Renders an explicit loading affordance instead of a blank
   * drawer body; takes precedence over every other state. */
  loading?: boolean;
  /** Set when fetching the source (or its highlights) failed, or a stream
   * backing it dropped. Renders an explicit failure state and must never be
   * confused with a completed examination. */
  loadError?: string | null;
}

export function ExaminationDrawer({
  card,
  open,
  onClose,
  loading = false,
  loadError = null
}: ExaminationDrawerProps) {
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

  const examState = deriveExamState(card, loading, loadError);

  return (
    <aside
      ref={asideRef}
      className={[styles.exam, open ? styles.examOpen : ""].join(" ")}
      role="dialog"
      aria-modal="false"
      aria-label="Examination"
    >
      <header className={styles.examHead}>
        {examState.kind === "ready" ? (
          <span className={styles.examTierChip} data-tier={examState.disposition.tier}>
            {examState.disposition.label}
          </span>
        ) : (
          <span className={styles.examLabel}>Examination</span>
        )}
        {examState.kind === "ready" && typeof examState.card.claim_index === "number" ? (
          <span className={styles.examIndex}>claim {examState.card.claim_index + 1}</span>
        ) : null}
        <button
          type="button"
          className={styles.examClose}
          onClick={onClose}
          ref={closeRef}
          aria-label="Close"
        >
          ×
        </button>
      </header>
      {examState.kind === "loading" ? (
        <div className={styles.examBody}>
          <div className={styles.sourceLoading} role="status">
            <Spinner size={16} />
            <span>Loading the source…</span>
          </div>
        </div>
      ) : examState.kind === "load-error" ? (
        <div className={styles.examBody}>
          <p className={styles.errorBanner} role="alert">
            The source could not be loaded.
          </p>
          <p className={styles.sourceMuted}>{examState.message}</p>
        </div>
      ) : examState.kind === "empty" ? (
        <div className={styles.examBody} role="status">
          <p className={styles.sourceMuted}>No source to examine.</p>
          <p className={styles.sourceMuted}>Select a claim to open its examination.</p>
        </div>
      ) : examState.kind === "malformed" ? (
        <div className={styles.examBody}>
          <p className={styles.errorBanner} role="alert">
            This source could not be displayed.
          </p>
          <p className={styles.sourceMuted}>
            The record returned data in a shape this drawer did not expect.
          </p>
        </div>
      ) : (
        <div className={styles.examBody}>
          <blockquote className={styles.examClaim}>{examState.card.claim_text}</blockquote>
          <section className={styles.checks} aria-label="The four checks">
            <h3 className={styles.checksLabel}>The checks</h3>
            {examState.checks.map((ck) => (
              <div key={ck.name} className={styles.check} data-state={ck.state}>
                <span className={styles.checkGlyph} data-state={ck.state} aria-hidden="true">
                  {CHECK_GLYPH[ck.state] ?? "\u00B7"}
                </span>
                <div>
                  <span className={styles.checkName}>
                    {ck.name}
                    <span className={styles.checkWeight} data-weight={ck.weight}>
                      {ck.weight.toUpperCase()}
                    </span>
                  </span>
                  <p className={styles.checkDetail}>{ck.detail}</p>
                </div>
              </div>
            ))}
          </section>
          {(() => {
            // Per-citation register lines: each cited case named with the
            // honest label (coverage statements stay muted; a caption mismatch
            // is the flag by name). Re-homed from the retired live card.
            const cases = (examState.card.case_verdicts ?? []).flatMap((b) =>
              b?.ok
                ? ((b.verdicts ?? []) as Array<{
                    citation?: string;
                    case_name?: string | null;
                    exists?: boolean;
                    status?: number;
                    bounded_corpus?: boolean;
                    caption_mismatch?: boolean;
                  }>)
                : []
            );
            if (cases.length === 0) return null;
            return (
              <section className={styles.examCases} aria-label="Cited cases">
                {cases.map((v, i) => {
                  const reg = caseLineRegister(v);
                  return (
                    <p key={i} className={styles.examCaseLine} data-kind={reg.kind}>
                      <span>{v.citation}</span>
                      <span className={styles.examCaseLabel}> · {reg.label}</span>
                      {v.case_name ? <span> · {v.case_name}</span> : null}
                    </p>
                  );
                })}
              </section>
            );
          })()}
          <SourceInspectorBody card={examState.card} disposition={examState.disposition} />
        </div>
      )}
    </aside>
  );
}
