import { describe, expect, test } from "vitest";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type DispositionKind } from "./claimDisposition";

type CaseOver = Partial<{
  status: number;
  exists: boolean;
  holding_match: boolean | null;
  holding_error: string | null;
  caption_mismatch: boolean;
  holding_skipped: boolean;
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

  test("an unknown card with a T1 assessment renders the assistive 'assessed' tier, no number", () => {
    const d = dispositionForClaim(
      card({ verdict: "unknown", assessed_confidence: 80, assessed_label: "support" })
    );
    expect(d.kind).toBe("assessed");
    expect(d.tier).toBe("assistive");
    expect(d.label).toBe("Assessed (local model)");
    // D3: the confidence rides the wire for the gate but no number is ever rendered.
    expect(`${d.label} ${d.detail}`).not.toMatch(/\d/);
  });

  test("a T1 contradiction assessment stays the quiet assistive register, never a flag", () => {
    const d = dispositionForClaim(
      card({ verdict: "unknown", assessed_confidence: 95, assessed_label: "contradict" })
    );
    expect(d.kind).toBe("assessed");
    expect(d.tier).toBe("assistive");
    expect(`${d.label} ${d.detail}`).not.toMatch(/\d/);
  });

  test("an unknown card with no T1 assessment stays could_not_check", () => {
    const d = dispositionForClaim(card({ verdict: "unknown", assessed_confidence: null }));
    expect(d.kind).toBe("could_not_check");
  });

  test("a stray assessed_confidence never overrides a deterministic verdict (T0 precedence)", () => {
    // The assessed branch lives only inside verdict === "unknown"; a verified or
    // unsupported card carrying a stray assessment keeps its deterministic disposition.
    const verified = dispositionForClaim(card({ verdict: "verified", assessed_confidence: 99 }));
    expect(verified.kind).not.toBe("assessed");
    const unsupported = dispositionForClaim(
      card({ verdict: "unsupported", assessed_confidence: 99 })
    );
    expect(unsupported.kind).toBe("claim_unsupported");
  });

  test("the assessed tier sorts below the honest refusal and above clean passes", () => {
    expect(DISPOSITION_ORDER.assessed).toBeGreaterThan(DISPOSITION_ORDER.could_not_check);
    expect(DISPOSITION_ORDER.assessed).toBeLessThan(DISPOSITION_ORDER.supported);
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

  test("a contract 'present' finding stays supported but surfaces its hedge, never a bare check", () => {
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        case_verdicts: [],
        unsupported_reason: "two (2) years appears in Section 12; review the full clause for context."
      })
    );
    expect(d.kind).toBe("supported");
    expect(d.tier).toBe("pass");
    // The hedge must reach the reader: presence, not proof of truth.
    expect(d.detail).toContain("appears in Section 12");
    expect(d.detail).not.toBe("");
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

// Phase 7: the deterministic engine derives the top-line verdict from
// case-existence / contract results (services.verify._claim_dict_to_verdict).
// These lock how those cards render through the existing disposition logic.
describe("deterministic engine cards", () => {
  test("a fabricated cite is citation_not_found (the catch), whatever the verdict", () => {
    const d = dispositionForClaim(
      card({
        verdict: "unsupported",
        case_verdicts: [batch([caseItem({ status: 404, exists: false })])]
      })
    );
    expect(d.kind).toBe("citation_not_found");
    expect(d.tier).toBe("flag");
  });

  test("a real cite with holding off is a positive Citation verified, not a refusal", () => {
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        case_verdicts: [
          batch([caseItem({ status: 200, exists: true, holding_match: null, holding_skipped: true })])
        ]
      })
    );
    expect(d.kind).toBe("supported");
    expect(d.tier).toBe("pass");
    expect(d.label).toBe("Citation verified");
  });

  test("a real cite whose holding check ERRORED is could_not_check", () => {
    const d = dispositionForClaim(
      card({
        verdict: "verified",
        case_verdicts: [
          batch([caseItem({ status: 200, exists: true, holding_match: null, holding_error: "fetch failed" })])
        ]
      })
    );
    expect(d.kind).toBe("could_not_check");
  });

  test("a contract parametric contradiction is claim_unsupported with its detail", () => {
    const d = dispositionForClaim(
      card({
        verdict: "unsupported",
        case_verdicts: [],
        unsupported_reason: "the claim's money value contradicts the clause"
      })
    );
    expect(d.kind).toBe("claim_unsupported");
    expect(d.detail).toContain("contradict");
  });

  test("a contract not_found is could_not_check, not an accusatory flag", () => {
    const d = dispositionForClaim(
      card({
        verdict: "unknown",
        case_verdicts: [],
        unsupported_reason: "the claim's language does not appear in the clause"
      })
    );
    expect(d.kind).toBe("could_not_check");
    expect(d.tier).toBe("refusal");
  });

  test("a contract present is supported", () => {
    const d = dispositionForClaim(card({ verdict: "verified", case_verdicts: [] }));
    expect(d.kind).toBe("supported");
  });

  test("a caption mismatch (real number, wrong case name) is citation_not_found", () => {
    const d = dispositionForClaim(
      card({
        verdict: "unsupported",
        case_verdicts: [batch([caseItem({ status: 200, exists: true, caption_mismatch: true })])]
      })
    );
    expect(d.kind).toBe("citation_not_found");
    expect(d.tier).toBe("flag");
    expect(d.detail).toContain("different case");
  });

  test("a no-anchor claim is could_not_check, never an accusatory unsupported", () => {
    const d = dispositionForClaim(
      card({
        verdict: "unknown",
        case_verdicts: [],
        unsupported_reason:
          "No verifiable anchor (citation, quotation, amount, or date) was found, so this statement was not independently checked."
      })
    );
    expect(d.kind).toBe("could_not_check");
    expect(d.tier).toBe("refusal");
    expect(d.detail).toContain("not independently checked");
  });
});
