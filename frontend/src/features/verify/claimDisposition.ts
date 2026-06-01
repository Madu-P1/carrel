/**
 * Carrel V2 verify surface, per-claim disposition.
 *
 * Re-projects the engine's raw per-claim signals (grounding verdict,
 * CourtListener case-existence, holding-match, engine error) into the
 * litigator-legible taxonomy the cross-professional discovery converged on
 * (docs/notes/2026-05-29-cachet-cross-professional-discovery.md):
 *
 *   supported               the unmarked default; the absence of a flag is the pass
 *   citation_not_found      a cited case does not resolve to a real case (the fabrication flag)
 *   proposition_unsupported the cited case is real but does not stand for the claim
 *   claim_unsupported       we checked the loaded sources and found no support
 *   could_not_check         we could not check (no source loaded, ambiguous cite,
 *                           verification unavailable). The honest refusal, full weight.
 *
 * The product attests to grounding, never to truth. A "supported" disposition
 * means "this matches a source you gave me," not "this is correct." Anything we
 * could not fully check is surfaced as could_not_check rather than waved through
 * as supported, because a silent pass is the one disqualifying behavior.
 *
 * Pure and deterministic. No confidence scores anywhere, by design.
 *
 * NOTE: a true "quote altered" disposition (the draft's quotation does not match
 * the cited source verbatim) is intentionally absent. The current engine grounds
 * its own extracted quotes, not the user's draft quotes, so it cannot honestly
 * emit that signal yet. It is scoped as a fast-follow; we do not render a state
 * we cannot populate.
 */
import type { VerifyClaimVerdict } from "@/services/api/endpoints";

export type DispositionKind =
  | "supported"
  | "citation_not_found"
  | "proposition_unsupported"
  | "claim_unsupported"
  | "could_not_check";

/**
 * Rendering register, distinct from the kind. Deterministic facts wear the
 * loud oxblood "flag": a cited case that does not resolve, a claim with no
 * support in the loaded sources. An AI judgment about a real source, the
 * holding / proposition match, wears the quieter "assistive" register instead:
 * a margin note left for the lawyer's own review, never a confident accusation.
 * A false-confident holding shown as a hard flag ends careers.
 */
export type DispositionTier = "pass" | "flag" | "assistive" | "refusal";

export interface ClaimDisposition {
  kind: DispositionKind;
  tier: DispositionTier;
  /** Litigator-facing headline label. */
  label: string;
  /** One-line plain-language reason. Empty for the unmarked pass. */
  detail: string;
}

/** Sort order, worst-first by severity and independent of the render register:
 * the fabricated citation, the wrong-proposition citation, and the ungrounded
 * claim, then the honest could-not-check, then the unmarked passes last. */
export const DISPOSITION_ORDER: Record<DispositionKind, number> = {
  citation_not_found: 0,
  proposition_unsupported: 1,
  claim_unsupported: 2,
  could_not_check: 3,
  supported: 4
};

const TIER: Record<DispositionKind, DispositionTier> = {
  citation_not_found: "flag",
  // A real case cited for a proposition it does not support is an AI judgment,
  // not a deterministic fact, so it renders assistive ("for your review"),
  // never the oxblood flag that citation_not_found and claim_unsupported wear.
  proposition_unsupported: "assistive",
  claim_unsupported: "flag",
  could_not_check: "refusal",
  supported: "pass"
};

interface FlatCase {
  status: number;
  exists: boolean;
  holdingMatch: boolean | null;
  holdingError: string | null;
}

function flattenCases(card: VerifyClaimVerdict): { cases: FlatCase[]; batchError: boolean } {
  const batches = card.case_verdicts ?? [];
  const cases: FlatCase[] = [];
  let batchError = false;
  for (const batch of batches) {
    if (!batch?.ok) {
      batchError = true;
      continue;
    }
    for (const v of batch.verdicts ?? []) {
      cases.push({
        status: typeof v.status === "number" ? v.status : 0,
        exists: Boolean(v.exists),
        holdingMatch: v.holding_match ?? null,
        holdingError: v.holding_error ?? null
      });
    }
  }
  return { cases, batchError };
}

function reasonText(card: VerifyClaimVerdict): string | null {
  const r = card.unsupported_reason;
  return typeof r === "string" && r.trim() ? r.trim() : null;
}

function mk(kind: DispositionKind, label: string, detail: string): ClaimDisposition {
  return { kind, tier: TIER[kind], label, detail };
}

/**
 * Collapse one claim's signals into a single disposition. Precedence runs
 * worst-first: a fabricated citation outranks a wrong-proposition citation,
 * which outranks an ungrounded claim, which outranks an honest "could not
 * check." Only a fully clean, fully checked claim returns "supported."
 */
export function dispositionForClaim(card: VerifyClaimVerdict): ClaimDisposition {
  const { cases, batchError } = flattenCases(card);

  // A cited case that does not resolve (404) or is malformed (400) is the
  // loudest flag: the fabricated-citation nightmare. It outranks everything,
  // including a claim whose surrounding prose was otherwise grounded.
  const fabricated = cases.some((c) => c.status === 404 || c.status === 400);
  if (fabricated) {
    return mk(
      "citation_not_found",
      "Citation not found",
      "No case matching this citation was found in the record checked."
    );
  }

  // A real case cited for a proposition it does not support.
  const propositionUnsupported = cases.some((c) => c.exists && c.holdingMatch === false);
  if (propositionUnsupported) {
    return mk(
      "proposition_unsupported",
      "Source does not support this",
      "The cited case is real but does not stand for this claim."
    );
  }

  // Dimensions that could not be finished: an ambiguous citation (multiple
  // matches), a rate-limited or errored lookup, or a holding check that could
  // not run. None of these may be waved through as supported.
  const ambiguousCite = cases.some((c) => c.status === 300);
  const caseLookupError =
    batchError ||
    cases.some(
      (c) =>
        c.status === 429 ||
        (!c.exists && c.status !== 404 && c.status !== 400 && c.status !== 300)
    );
  const holdingUncheckable = cases.some(
    (c) => c.exists && (c.holdingError !== null || c.holdingMatch === null)
  );

  if (card.verdict === "unsupported") {
    return mk(
      "claim_unsupported",
      "Unsupported by your sources",
      reasonText(card) ?? "Nothing in the loaded sources supports this statement."
    );
  }
  if (card.verdict === "unknown") {
    return mk(
      "could_not_check",
      "Could not verify",
      reasonText(card) ??
        "Verification could not run. Load the sources this draft relies on, then verify again."
    );
  }

  // verdict === "verified": grounded in the user's sources. Downgrade to the
  // honest refusal if any cited authority could not be fully checked.
  if (ambiguousCite) {
    return mk(
      "could_not_check",
      "Could not verify",
      "Grounded in your sources, but the citation matches more than one case. Confirm which one you mean."
    );
  }
  if (caseLookupError) {
    return mk(
      "could_not_check",
      "Could not verify",
      "Grounded in your sources, but the citation could not be checked. Try again, or open the source to confirm."
    );
  }
  if (holdingUncheckable) {
    return mk(
      "could_not_check",
      "Could not verify",
      "Grounded in your sources, but the cited opinion could not be read to confirm it supports the claim."
    );
  }
  return mk("supported", "Supported", "");
}
