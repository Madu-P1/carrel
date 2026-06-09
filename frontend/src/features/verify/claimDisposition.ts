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
 *   assessed                a local model (T1, ADR-0012) assessed this anchor-free
 *                           claim above the calibration threshold; the quiet assistive
 *                           register, for the lawyer's review, never a verified/flag.
 *
 * The product attests to grounding, never to truth. A "supported" disposition
 * means "this matches a source you gave me," not "this is correct." Anything we
 * could not fully check is surfaced as could_not_check rather than waved through
 * as supported, because a silent pass is the one disqualifying behavior.
 *
 * Pure and deterministic mapping. The T1 "assessed" tier reflects a local-model
 * judgment whose confidence rides the wire for the calibration gate but is never
 * rendered as a score on the card (D3): no confidence number appears in the UI, by design.
 *
 * NOTE: the deterministic engine checks the user's draft quotes against the cited
 * opinion text it holds. A quote it cannot confirm verbatim is surfaced as
 * could_not_check (an honest refusal), never an "altered/unsupported" accusation,
 * because the bundled opinion text is not guaranteed complete. The LLM path's
 * brief-level quote panel, which grounds against a retrieved source pool, can still
 * report a true "altered" status separately.
 */
import type { VerifyClaimVerdict } from "@/services/api/endpoints";

export type DispositionKind =
  | "supported"
  | "citation_not_found"
  | "proposition_unsupported"
  | "claim_unsupported"
  | "assessed"
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
  // T1 assistive assessment sorts below the deterministic taxonomy and the honest
  // refusal (a soft model judgment never outranks a known gap), above clean passes.
  assessed: 4,
  supported: 5
};

const TIER: Record<DispositionKind, DispositionTier> = {
  citation_not_found: "flag",
  // A real case cited for a proposition it does not support is an AI judgment,
  // not a deterministic fact, so it renders assistive ("for your review"),
  // never the oxblood flag that citation_not_found and claim_unsupported wear.
  proposition_unsupported: "assistive",
  claim_unsupported: "flag",
  could_not_check: "refusal",
  // T1 (ADR-0012): a local-model assessment is an AI judgment, so it wears the same
  // quiet assistive register, never a verified pass or an oxblood flag.
  assessed: "assistive",
  supported: "pass"
};

interface FlatCase {
  status: number;
  exists: boolean;
  holdingMatch: boolean | null;
  holdingError: string | null;
  // Deterministic engine only (read with a cast in flattenCases; not on the wire
  // schema). captionMismatch: the number resolved but to a different case than
  // named. holdingSkipped: holding-match was off, so a null holding result is
  // "not evaluated", distinct from the LLM path's "ran but could not determine".
  captionMismatch: boolean;
  holdingSkipped: boolean;
  // Deterministic path only: this verdict came from the BOUNDED offline corpus, so an
  // absent cite is "outside my coverage" (could-not-check), not a national "does not exist".
  boundedCorpus: boolean;
  // The corpus's own manifest (D13), when it carried one: what scope of corpus
  // the check ran against and the snapshot date. Lets the copy name the
  // denominator ("a 3-case demo corpus, as of 2026-06-05") instead of a vague
  // "offline corpus", and lets a complete-index miss state its as-of date.
  corpusScope: string | null;
  corpusCaseCount: number | null;
  corpusAsOf: string | null;
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
        holdingError: v.holding_error ?? null,
        captionMismatch: Boolean((v as { caption_mismatch?: boolean }).caption_mismatch),
        holdingSkipped: Boolean((v as { holding_skipped?: boolean }).holding_skipped),
        boundedCorpus: Boolean((v as { bounded_corpus?: boolean }).bounded_corpus),
        corpusScope: (v as { corpus_scope?: string }).corpus_scope ?? null,
        corpusCaseCount: (v as { corpus_case_count?: number }).corpus_case_count ?? null,
        corpusAsOf: (v as { corpus_as_of?: string }).corpus_as_of ?? null
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
  const captionMismatch = cases.some((c) => c.captionMismatch);
  // A bounded-corpus 404/400 is NOT fabricated: the offline corpus cannot tell a
  // fabricated cite from a real-but-unbundled one, so it is handled as could-not-check
  // below. A national 404 (no boundedCorpus flag) and any caption mismatch still flag.
  const nationalMiss = cases.find(
    (c) => (c.status === 404 || c.status === 400) && !c.boundedCorpus
  );
  const fabricated = Boolean(nationalMiss) || captionMismatch;
  if (fabricated) {
    return mk(
      "citation_not_found",
      "Citation not found",
      captionMismatch
        ? "This citation number resolves to a different case than the one named in the draft."
        : nationalMiss?.corpusAsOf
          ? `No such case appears in the citation index checked (complete as of ${nationalMiss.corpusAsOf}).`
          : "No case matching this citation was found in the record checked."
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

  // #1 (three-state existence): a cite absent from the BOUNDED offline corpus is
  // "outside my coverage", an honest could-not-check, never the oxblood fabrication
  // flag. The bundled corpus is not the national database, so a real-but-unbundled
  // case must not be called fake. A caption mismatch is already flagged above; a
  // national 404 (no boundedCorpus flag) was treated as fabricated above.
  const outsideCoverage = cases.find(
    (c) =>
      c.boundedCorpus && !c.exists && !c.captionMismatch && (c.status === 404 || c.status === 400)
  );
  if (outsideCoverage) {
    const scope =
      outsideCoverage.corpusScope && outsideCoverage.corpusCaseCount && outsideCoverage.corpusAsOf
        ? ` (a ${outsideCoverage.corpusCaseCount}-case ${outsideCoverage.corpusScope} corpus, as of ${outsideCoverage.corpusAsOf})`
        : "";
    return mk(
      "could_not_check",
      "Could not verify",
      `This citation is outside the offline corpus checked${scope}. Confirm it against the full national database.`
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
  // "Could not check" covers a real holding ERROR, and the LLM path's "ran but
  // could not determine" (holding null while NOT skipped). Holding being off
  // (null + skipped) is not a failure and is rendered as a positive confirmation
  // below.
  const holdingUncheckable = cases.some(
    (c) => c.exists && (c.holdingError !== null || (c.holdingMatch === null && !c.holdingSkipped))
  );

  if (card.verdict === "unsupported") {
    return mk(
      "claim_unsupported",
      "Unsupported by your sources",
      reasonText(card) ?? "Nothing in the loaded sources supports this statement."
    );
  }
  if (card.verdict === "unknown") {
    // T1 recall tier (ADR-0012): a local model assessed this anchor-free claim above
    // the calibration threshold. It rides the quiet `assistive` register (a margin note
    // for review), never a verified/flag, and never overrides a T0 disposition: the
    // deterministic flag, unsupported, and verified branches above have already
    // returned, so only a genuinely could-not-check card reaches here. A verified or
    // unsupported card carrying a stray assessed_confidence keeps its deterministic
    // disposition because it never enters this branch. assessed_confidence stays on the
    // wire for the gate; D3 keeps it off the card, so no number is rendered.
    if (card.assessed_confidence != null) {
      const direction =
        card.assessed_label === "contradict"
          ? "suggests this may not match your sources"
          : card.assessed_label === "support"
            ? "assessed this as matching your sources"
            : "assessed this against your sources";
      return mk(
        "assessed",
        "Assessed (local model)",
        `A local model ${direction}, for your review. Not a deterministic verification.`
      );
    }
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
  // The cited case exists but its holding was not evaluated (the assistive
  // holding-match check is off). An honest positive confirmation: not a refusal,
  // and not a claim of full support.
  const existsUnevaluated = cases.some(
    (c) => c.exists && c.holdingMatch === null && c.holdingError === null && c.holdingSkipped
  );
  if (existsUnevaluated) {
    return mk(
      "supported",
      "Citation verified",
      "The cited case exists in the record checked. Whether it supports your proposition was not evaluated."
    );
  }
  // A contract "present" finding: the value or quoted language appears verbatim in
  // a named clause. Positive (green), but the hedge detail keeps it honest, that
  // this attests the language is PRESENT, not that the surrounding claim is true.
  const presenceHedge = reasonText(card);
  if (presenceHedge) {
    return mk("supported", "Present in your sources", presenceHedge);
  }
  return mk("supported", "Supported", "");
}
