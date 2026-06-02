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
  /** A surfaced stream error, or null. */
  error: string | null;
}

export function initialStreamState(): VerifyStreamState {
  return { phase: "idle", cards: [], checked: new Set(), result: null, error: null };
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
    case "result":
      return { ...state, phase: "done", result: event.verify };
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
 * Returns false once the stream is done/errored: at that point the settled
 * `result` (or the dropped-stream fallback) governs, not this transient flag.
 */
export function isCardChecking(state: VerifyStreamState, card: VerifyClaimVerdict): boolean {
  if (state.phase !== "checking") return false;
  const index = card.claim_index;
  if (typeof index !== "number") return false;
  return !state.checked.has(index);
}

/** How many skeleton cards have received their cite_verdict (for the progress line). */
export function checkedProgress(state: VerifyStreamState): { checked: number; total: number } {
  return { checked: state.checked.size, total: state.cards.length };
}
