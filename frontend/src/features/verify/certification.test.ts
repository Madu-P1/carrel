import { describe, expect, test } from "vitest";

import type { VerifyResponse } from "@/services/api/endpoints";

import {
  attestationFor,
  buildCertification,
  certificationToJson,
  fingerprintDraft,
  isLocalExecution,
  sealStateFor
} from "./certification";

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
  test("is a 64-char hex string", () => {
    expect(fingerprintDraft("anything")).toMatch(/^[0-9a-f]{64}$/);
  });
  test("empty text is the SHA-256 of the empty string", () => {
    expect(fingerprintDraft("")).toBe(
      "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    );
  });
  test("matches the known SHA-256 vector for 'abc'", () => {
    expect(fingerprintDraft("abc")).toBe(
      "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    );
  });
});

describe("sealStateFor", () => {
  test("no seal set yet is unsealed", () => {
    expect(sealStateFor(null, "abc")).toBe("unsealed");
  });
  test("a seal whose fingerprint still matches the draft is sealed", () => {
    expect(sealStateFor("abc", "abc")).toBe("sealed");
  });
  test("a seal whose draft has since changed is cracked", () => {
    expect(sealStateFor("abc", "def")).toBe("cracked");
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

// Phase 8: filing-grade audit artifact (local/cloud provenance, attestation,
// per-source fingerprints, machine-readable export).
describe("audit artifact provenance", () => {
  test("local providers are local; cloud is not", () => {
    expect(isLocalExecution("deterministic")).toBe(true);
    expect(isLocalExecution("afm")).toBe(true);
    expect(isLocalExecution("ollama")).toBe(true);
    expect(isLocalExecution("claude")).toBe(false);
    expect(isLocalExecution("")).toBe(false);
    // Fail-safe: unrecognized provider is never local, so locality is never over-claimed.
    expect(isLocalExecution("unknown")).toBe(false);
    expect(attestationFor("unknown")).toContain("cloud");
  });

  test("attestation states no data left the device for local, and is honest for cloud", () => {
    expect(attestationFor("deterministic")).toContain("No data left this device");
    const cloud = attestationFor("claude");
    expect(cloud).toContain("claude");
    expect(cloud).toContain("cloud");
  });

  test("a local MODEL never earns the no-egress attestation", () => {
    // afm/ollama mean the language model ran on-device, but the grounding path
    // those providers ride can still reach live citation lookups, so the
    // artifact must never attest no-egress for them. Only the deterministic
    // engine, offline by construction, makes that claim.
    for (const provider of ["afm", "ollama"]) {
      const text = attestationFor(provider);
      expect(text).not.toContain("No data left this device");
      expect(text).toContain("on this device");
      expect(text).toContain("network");
    }
  });

  test("buildCertification records local execution + attestation from the provider", () => {
    const local = buildCertification(resp({ provider: "deterministic", claim_verdicts: [supported] }), AT);
    expect(local.localExecution).toBe(true);
    expect(local.attestation).toContain("No data left this device");

    const cloud = buildCertification(resp({ provider: "claude", claim_verdicts: [supported] }), AT);
    expect(cloud.localExecution).toBe(false);
  });

  test("each certified item carries a per-source SHA-256 aligned with its sources", () => {
    const m = buildCertification(resp({ claim_verdicts: [supported] }), AT);
    const item = m.allItems[0];
    expect(item.sourceFingerprints).toHaveLength(item.sources.length);
    for (const fp of item.sourceFingerprints) expect(fp).toMatch(/^[0-9a-f]{64}$/);
  });

  test("certificationToJson is valid JSON carrying a schema version and the attestation", () => {
    const m = buildCertification(resp({ provider: "deterministic", claim_verdicts: [supported] }), AT);
    const parsed = JSON.parse(certificationToJson(m));
    expect(parsed.schema_version).toBe(1);
    expect(parsed.localExecution).toBe(true);
    expect(parsed.attestation).toContain("No data left this device");
    expect(parsed.fingerprint).toMatch(/^[0-9a-f]{64}$/);
  });

  test("coverage counts ride the certification when the engine provides them", () => {
    // Coverage honesty: the exhibit must be able to state the denominator
    // (what was examined vs what carried nothing checkable), so the model
    // carries the deterministic path's counts verbatim.
    const m = buildCertification(
      resp({
        provider: "deterministic",
        claim_verdicts: [supported],
        coverage: { statements: 12, treated: 3, untreated: 9 }
      }),
      AT
    );
    expect(m.coverage).toEqual({ statements: 12, treated: 3, untreated: 9 });
    const parsed = JSON.parse(certificationToJson(m));
    expect(parsed.coverage).toEqual({ statements: 12, treated: 3, untreated: 9 });
  });

  test("coverage is null when the engine cannot count (LLM path)", () => {
    const m = buildCertification(resp({ provider: "claude", claim_verdicts: [supported] }), AT);
    expect(m.coverage).toBeNull();
  });
});
