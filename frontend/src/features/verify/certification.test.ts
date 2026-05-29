import { describe, expect, test } from "vitest";

import type { VerifyResponse } from "@/services/api/endpoints";

import { buildCertification, fingerprintDraft } from "./certification";

function resp(over: Partial<Record<string, unknown>> = {}): VerifyResponse {
  return {
    draft_text: "Some draft.",
    claim_verdicts: [],
    summary: { total: 0, verified: 0, unsupported: 0, unknown: 0 },
    latency_ms: 0,
    model: "",
    ok: true,
    provider: "claude",
    ...over
  } as unknown as VerifyResponse;
}

const AT = "2026-05-29T12:00:00.000Z";

const supported = {
  claim_index: 0,
  claim_text: "A grounded statement.",
  verdict: "verified",
  citations: [
    {
      node_id: 3,
      document_id: "d1",
      document_name: "Brief.pdf",
      section: null,
      page_num: 12,
      snippet: "",
      content: "",
      score: 0.5,
      label: "",
      node_type: "body"
    }
  ],
  case_verdicts: [],
  unsupported_reason: null
};

const fabricated = {
  claim_index: 1,
  claim_text: "Cites a fake case.",
  verdict: "verified",
  citations: [],
  case_verdicts: [
    {
      claim_index: 1,
      ok: true,
      error_code: null,
      error_message: null,
      verdicts: [
        {
          citation: "999 U.S. 999",
          normalized_citation: null,
          status: 404,
          exists: false,
          case_name: null,
          absolute_url: null,
          court: null,
          date_filed: null,
          error_message: null,
          holding_match: null,
          holding_concern: null,
          holding_excerpt: null,
          holding_error: null
        }
      ]
    }
  ],
  unsupported_reason: null
};

describe("fingerprintDraft", () => {
  test("is stable for the same text", () => {
    expect(fingerprintDraft("hello world")).toBe(fingerprintDraft("hello world"));
  });
  test("differs for different text", () => {
    expect(fingerprintDraft("a")).not.toBe(fingerprintDraft("b"));
  });
  test("is an 8-char hex string", () => {
    expect(fingerprintDraft("anything")).toMatch(/^[0-9a-f]{8}$/);
  });
  test("empty text is the FNV offset basis", () => {
    expect(fingerprintDraft("")).toBe("811c9dc5");
  });
});

describe("buildCertification", () => {
  test("counts the not-confirmed set as needsReview and lists it worst-first", () => {
    const m = buildCertification(resp({ draft_text: "x", claim_verdicts: [supported, fabricated] }), AT);
    expect(m.totalStatements).toBe(2);
    expect(m.needsReviewCount).toBe(1);
    expect(m.counts.citation_not_found).toBe(1);
    expect(m.counts.supported).toBe(1);
    expect(m.flagged[0].label).toBe("Citation not found");
    expect(m.flagged[0].kind).toBe("citation_not_found");
  });

  test("ties the fingerprint to the checked draft text", () => {
    const m = buildCertification(resp({ draft_text: "the exact draft" }), AT);
    expect(m.fingerprint).toBe(fingerprintDraft("the exact draft"));
  });

  test("all-supported still produces a model with an empty flagged set", () => {
    const m = buildCertification(resp({ claim_verdicts: [supported] }), AT);
    expect(m.needsReviewCount).toBe(0);
    expect(m.flagged).toEqual([]);
  });

  test("carries source provenance for the certified items", () => {
    const m = buildCertification(resp({ claim_verdicts: [supported] }), AT);
    expect(m.allItems[0].sources).toContain("Brief.pdf, p. 12");
  });

  test("no item label contains a percentage", () => {
    const m = buildCertification(resp({ draft_text: "x", claim_verdicts: [supported, fabricated] }), AT);
    for (const it of m.allItems) expect(it.label).not.toContain("%");
  });
});
