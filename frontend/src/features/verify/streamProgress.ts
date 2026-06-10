/**
 * Cachet PR3 — pure fold of the verify SSE stream into a render model.
 *
 * The streaming verify endpoint emits, in order: a `progress` event, a
 * `claims` skeleton (cards WITHOUT case verdicts), one `cite_verdict` per
 * claim as its CourtListener + holding-match check lands, then a `result`
 * carrying the canonical VerifyResponse.
 *
 * This module is the single, pure, unit-testable place that decides what the
 * UI shows mid-stream. It exists so the safety-critical rule lives in tested
 * logic, not in JSX: a claim that has NOT yet received its cite_verdict is
 * "checking" — never rendered as a pass. That enforces invariant #6 (an
 * unfinished verification must never read as supported) for the live view; the
 * final, settled view is driven by the `result` payload through the existing
 * `dispositionForClaim`, unchanged.
 */
import type {
  VerifyClaimVerdict,
  VerifyQuoteResult,
  VerifyResponse,
  VerifyStreamEvent
} from "@/services/api/endpoints";

export type StreamPhase = "idle" | "extracting" | "claims" | "checking" | "done" | "error";

export interface VerifyStreamState {
  phase: StreamPhase;
  /** Skeleton cards from the `claims` event; [] until it arrives. */
  cards: VerifyClaimVerdict[];
  /** claim_index values whose cite_verdict has landed. */
  checked: Set<number>;
  /** The canonical response, set only on the `result` event. */
  result: VerifyResponse | null;
  /** Brief-level draft-quote-verbatim results (Cachet PR4). Set on the
   *  `quote_batch` event (the live reveal) and reconciled from `result`. [] when
   *  the draft had no quoted spans. Brief-level: not per-claim (PR5 aligns). */
  quotes: VerifyQuoteResult[];
  /** A surfaced stream error, or null. */
  error: string | null;
}

export function initialStreamState(): VerifyStreamState {
  return { phase: "idle", cards: [], checked: new Set(), result: null, quotes: [], error: null };
}

/**
 * Fold one stream event into the state, returning a NEW state object (Preact
 * signal/setState friendly; never mutates the input). `checked` is copied on
 * write so referential-equality checks downstream stay honest.
 */
export function reduceStreamEvent(
  state: VerifyStreamState,
  event: VerifyStreamEvent
): VerifyStreamState {
  switch (event.type) {
    case "progress":
      return { ...state, phase: "extracting" };
    case "claims":
      return {
        ...state,
        phase: "checking",
        cards: event.claim_verdicts ?? []
      };
    case "cite_verdict": {
      const checked = new Set(state.checked);
      checked.add(event.claim_index);
      // Patch the landed verdict onto its card so the live disposition reflects
      // the REAL cite outcome, not the empty skeleton. Without this a verified
      // (grounded) claim whose cited case is fabricated (404) or contradicts the
      // holding would render "Supported" the instant isCardChecking flips false,
      // for the whole remaining open-stream window — invariant #6's exact
      // forbidden behavior. With it, a landed 404 renders "Citation not found",
      // a contradiction renders the assistive register, only a clean cite passes.
      const cards = state.cards.map((card) =>
        card.claim_index === event.claim_index
          ? { ...card, case_verdicts: [event.case_verdict] }
          : card
      );
      return { ...state, checked, cards };
    }
    case "quote_batch":
      return { ...state, quotes: event.quotes ?? [] };
    case "result":
      // Reconcile quotes from the settled payload so a reload / non-stream
      // caller (no live quote_batch) still shows them; the live quote_batch and
      // the payload are computed from the same source, so they agree.
      return {
        ...state,
        phase: "done",
        result: event.verify,
        quotes: event.verify?.quote_results ?? state.quotes
      };
    case "error":
      return { ...state, phase: "error", error: event.error };
    default:
      return state;
  }
}

/**
 * Is this skeleton card still awaiting its cite_verdict? A card is "checking"
 * once the claims skeleton is in and before either its cite_verdict lands or
 * the final result settles. Index is the claim_index, which the backend emits
 * on every card and every cite_verdict so the two align.
 *
 * Returns false once the stream is done: at that point the settled `result`
 * governs. On "error" an UN-checked card stays checking: the skeleton carries
 * the grounding verdict with no case verdicts, so releasing it would render
 * "Supported" for a claim whose cite check never ran (invariant #6). The hosts
 * also unmount the live list on error; this is defense in depth for any render
 * path that still holds the cards.
 */
export function isCardChecking(state: VerifyStreamState, card: VerifyClaimVerdict): boolean {
  if (state.phase !== "checking" && state.phase !== "error") return false;
  const index = card.claim_index;
  // Without a claim_index the card can never be matched to a cite_verdict;
  // hold it as checking rather than release it to its skeleton disposition.
  if (typeof index !== "number") return true;
  return !state.checked.has(index);
}

/** How many skeleton cards have received their cite_verdict (for the progress line). */
export function checkedProgress(state: VerifyStreamState): { checked: number; total: number } {
  return { checked: state.checked.size, total: state.cards.length };
}
