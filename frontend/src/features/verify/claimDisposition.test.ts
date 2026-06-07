import { describe, expect, test } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type DispositionKind } from "./claimDisposition";

type CaseOver = Partial<{
  status: number;
  exists: boolean;
  holding_match: boolean | null;
  holding_error: string | null;
}>;

function caseItem(over: CaseOver = {}) {
  return {
    citation: "576 U.S. 644",
    normalized_citation: null,
    status: 200,
    exists: true,
    case_name: null,
    absolute_url: null,
    court: null,
    date_filed: null,
    error_message: null,
    holding_match: null,
    holding_concern: null,
    holding_excerpt: null,
    holding_error: null,
    ...over
  };
}

function batch(
  verdicts: ReturnType<typeof caseItem>[],
  ok = true,
  errorCode: string | null = null
) {
  return { claim_index: 0, ok, verdicts, error_code: errorCode, error_message: null };
}

function card(over: Partial<Record<string, unknown>> = {}): VerifyClaimVerdict {
  return {
    claim_index: 0,
    claim_text: "A statement.",
    verdict: "verified",
    citations: [],
    case_verdicts: [],
    unsupported_reason: null,
    ...over
  } as unknown as VerifyClaimVerdict;
}

describe("dispositionForClaim", () => {
  test("a cited case that does not exist (404) is citation_not_found", () => {
    const d = dispositionForClaim(
      card({ verdict: "verified", case_verdicts: [batch([caseItem({ status: 404, exists: false })])] })
    );
    expect(d.kind).toBe("citation_not_found");
    expect(d.tier).toBe("flag");
  });

  test("a malformed citation (400) is citation_not_found", () => {
    const d = dispositionForClaim(card({ case_verdicts: [batch([caseItem({ status: 400, exists: false })])] }));
    expect(d.kind).toBe("citation_not_found");
  });

  test("a fabricated citation outranks otherwise-grounded prose", () => {
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        citations: [{}],
        case_verdicts: [batch([caseItem({ status: 404, exists: false })])]
      })
    );
    expect(d.kind).toBe("citation_not_found");
  });

  test("a real case whose holding does not match is proposition_unsupported", () => {
    const d = dispositionForClaim(
      card({ case_verdicts: [batch([caseItem({ exists: true, status: 200, holding_match: false })])] })
    );
    expect(d.kind).toBe("proposition_unsupported");
    expect(d.tier).toBe("assistive");
  });

  test("a holding mismatch renders the assistive tier, never the oxblood flag", () => {
    // PR1 safety split: an AI judgment that a real, existing case does not stand
    // for the claim (holding_match === false) is assistive ("for your review"),
    // NOT a deterministic flag. This locks the TIER, the value the verify view
    // switches on to pick a badge / edge treatment; the assistive-vs-oxblood
    // rendering itself is verified at the craft human gate (no golden reference
    // yet). The deterministic flags (citation_not_found, claim_unsupported) keep
    // tier "flag" in their own tests above; together they lock the two registers
    // apart. A false-confident holding shown as a hard flag ends careers.
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        case_verdicts: [batch([caseItem({ exists: true, status: 200, holding_match: false })])]
      })
    );
    expect(d.kind).toBe("proposition_unsupported");
    expect(d.tier).toBe("assistive");
    expect(d.tier).not.toBe("flag");
  });

  test("verdict unsupported is claim_unsupported", () => {
    const d = dispositionForClaim(card({ verdict: "unsupported" }));
    expect(d.kind).toBe("claim_unsupported");
    expect(d.tier).toBe("flag");
  });

  test("verdict unknown is could_not_check (the honest refusal)", () => {
    const d = dispositionForClaim(card({ verdict: "unknown" }));
    expect(d.kind).toBe("could_not_check");
    expect(d.tier).toBe("refusal");
  });

  test("the refusal carries a precise next action (SM-V5), other dispositions do not", () => {
    // The calibrating "do this" turns abstention into a step the user can take.
    const refusal = dispositionForClaim(card({ verdict: "unknown" }));
    expect(refusal.nextAction).toBeTruthy();
    expect(refusal.nextAction).toMatch(/verify again/i);
    // It is not more uncertainty: the action is distinct from the explanation.
    expect(refusal.nextAction).not.toBe(refusal.detail);

    const supported = dispositionForClaim(card({ verdict: "verified" }));
    expect(supported.nextAction).toBeUndefined();
    const flag = dispositionForClaim(
      card({ case_verdicts: [batch([caseItem({ status: 404, exists: false })])] })
    );
    expect(flag.nextAction).toBeUndefined();
  });

  test("the refusal states what it checked and a button verb (C1), and never shrugs (C2)", () => {
    // Rubric C1: the refusal is the most COMPLETE card — it opens with the work
    // Cachet did (`checked`) and ends in a button verb (`actionLabel`). C2: it
    // never shrugs; it leads with what it did, not "could not check / run".
    const refusal = dispositionForClaim(card({ verdict: "unknown" }));
    expect(refusal.checked).toBeTruthy();
    expect(refusal.actionLabel).toBeTruthy();
    expect(refusal.checked?.toLowerCase()).not.toContain("could not");
    expect(refusal.detail.toLowerCase()).not.toContain("could not run");
    // The three parts are distinct: what was checked, what cannot be said, the action.
    expect(refusal.checked).not.toBe(refusal.detail);
    expect(refusal.actionLabel).not.toBe(refusal.nextAction);

    // checked/actionLabel are refusal-only; no other disposition carries them.
    const supported = dispositionForClaim(card({ verdict: "verified" }));
    expect(supported.checked).toBeUndefined();
    expect(supported.actionLabel).toBeUndefined();
    const flag = dispositionForClaim(
      card({ case_verdicts: [batch([caseItem({ status: 404, exists: false })])] })
    );
    expect(flag.checked).toBeUndefined();
    expect(flag.actionLabel).toBeUndefined();
  });

  test("verified prose with no citations is supported and unmarked", () => {
    const d = dispositionForClaim(card({ verdict: "verified" }));
    expect(d.kind).toBe("supported");
    expect(d.tier).toBe("pass");
    expect(d.detail).toBe("");
  });

  test("verified with a real case whose holding supports is supported", () => {
    const d = dispositionForClaim(
      card({ verdict: "verified", case_verdicts: [batch([caseItem({ exists: true, holding_match: true })])] })
    );
    expect(d.kind).toBe("supported");
  });

  test("a holding that could not be read downgrades verified to could_not_check", () => {
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        case_verdicts: [batch([caseItem({ exists: true, holding_match: null, holding_error: "fetch_failed" })])]
      })
    );
    expect(d.kind).toBe("could_not_check");
  });

  test("a refused holding (match null) downgrades verified to could_not_check", () => {
    const d = dispositionForClaim(
      card({ verdict: "verified", case_verdicts: [batch([caseItem({ exists: true, holding_match: null })])] })
    );
    expect(d.kind).toBe("could_not_check");
  });

  test("an ambiguous citation (300) downgrades verified to could_not_check", () => {
    const d = dispositionForClaim(
      card({ verdict: "verified", case_verdicts: [batch([caseItem({ status: 300, exists: false })])] })
    );
    expect(d.kind).toBe("could_not_check");
  });

  test("a failed case-lookup batch downgrades verified to could_not_check", () => {
    const d = dispositionForClaim(card({ verdict: "verified", case_verdicts: [batch([], false, "no_token")] }));
    expect(d.kind).toBe("could_not_check");
  });

  test("ordering is worst-first by severity, the refusal next, and supported last", () => {
    const kinds: DispositionKind[] = [
      "supported",
      "could_not_check",
      "citation_not_found",
      "claim_unsupported",
      "proposition_unsupported"
    ];
    const sorted = [...kinds].sort((a, b) => DISPOSITION_ORDER[a] - DISPOSITION_ORDER[b]);
    expect(sorted).toEqual([
      "citation_not_found",
      "proposition_unsupported",
      "claim_unsupported",
      "could_not_check",
      "supported"
    ]);
  });

  test("no disposition detail ever contains a percentage", () => {
    const samples = [
      card({ verdict: "verified" }),
      card({ verdict: "unsupported" }),
      card({ verdict: "unknown" }),
      card({ case_verdicts: [batch([caseItem({ status: 404, exists: false })])] }),
      card({ case_verdicts: [batch([caseItem({ exists: true, holding_match: false })])] })
    ];
    for (const c of samples) {
      expect(dispositionForClaim(c).detail).not.toContain("%");
    }
  });
});
