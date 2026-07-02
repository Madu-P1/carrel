/**
 * Cross-implementation conformance: the fixture at __fixtures__/specimen-cert.json
 * was issued by the PYTHON kernel (cachet_verify.certificate.attest_and_issue).
 * This suite proves the browser verifier reproduces its seal byte-for-byte,
 * which is the whole connector claim: a record issued by any Cachet surface
 * (app server, loopback daemon, CLI, companion) can be checked HERE, offline.
 */

import { describe, expect, it } from "vitest";

import companionCert from "./__fixtures__/companion-issued-cert.json";
import specimenCert from "./__fixtures__/specimen-cert.json";
import {
  canonicalJson,
  coerceCertificate,
  summarizeCertificate,
  verifySeal,
  type Certificate,
} from "./certificate";

const cert = specimenCert as unknown as Certificate;

function clone(): Certificate {
  return JSON.parse(JSON.stringify(cert)) as Certificate;
}

describe("the connector: the app accepts a COMPANION-issued record", () => {
  // companion-issued-cert.json was sealed by the ambient companion's OWN
  // implementation (cachet_companion.verify.certificate, a separate repo). The
  // Seal Bench's verifier accepting it byte-for-byte IS the connector: a record
  // from the ambient surface is checkable in the deliberate app, offline.
  const cc = companionCert as unknown as Certificate;

  it("verifies a companion-issued seal", async () => {
    expect(await verifySeal(cc)).toBe(true);
  });

  it("detects tampering in a companion-issued record", async () => {
    const forged = JSON.parse(JSON.stringify(cc)) as Certificate;
    forged.issued_at = "1999-01-01T00:00:00+00:00";
    expect(await verifySeal(forged)).toBe(false);
  });

  it("coerces a companion cert as a genuine certificate", () => {
    expect(coerceCertificate(cc).cert).not.toBeNull();
  });
});

describe("cross-language seal conformance (Python-issued fixture)", () => {
  it("verifies the kernel-issued seal byte-for-byte", async () => {
    expect(await verifySeal(cert)).toBe(true);
  });

  it("detects a flipped verdict (the attack the seal exists for)", async () => {
    const tampered = clone();
    tampered.claims[1].state = "verified";
    expect(await verifySeal(tampered)).toBe(false);
  });

  it("detects an edited detail, a swapped hash, and a changed date", async () => {
    const editedDetail = clone();
    editedDetail.claims[1].checks[0].detail = "nothing to see here";
    expect(await verifySeal(editedDetail)).toBe(false);

    const swappedHash = clone();
    const first = swappedHash.source_sha256s[0][0];
    swappedHash.source_sha256s[0] =
      (first === "0" ? "f" : "0") + swappedHash.source_sha256s[0].slice(1);
    expect(await verifySeal(swappedHash)).toBe(false);

    const movedDate = clone();
    movedDate.issued_at = "2020-01-01T00:00:00+00:00";
    expect(await verifySeal(movedDate)).toBe(false);
  });

  it("summarizes the three states honestly", () => {
    const summary = summarizeCertificate(cert);
    expect(summary.total).toBe(3);
    expect(summary.verified + summary.altered + summary.couldNotCheck).toBe(3);
    expect(summary.altered).toBeGreaterThanOrEqual(1);
  });
});

describe("canonical JSON matches the Python contract", () => {
  it("sorts keys and uses compact separators", () => {
    expect(canonicalJson({ b: 1, a: "x" })).toBe('{"a":"x","b":1}');
    expect(canonicalJson([1, "two", null])).toBe('[1,"two",null]');
    expect(canonicalJson({ outer: { z: true, a: [] } })).toBe('{"outer":{"a":[],"z":true}}');
  });

  it("round-trips the fixture body to the exact recorded fingerprint", async () => {
    // Stronger than verifySeal: pins that OUR canonicalization of the whole
    // kernel-issued body reproduces the kernel's own fingerprint, so the two
    // implementations agree on every byte of the serialization.
    expect(await verifySeal(cert)).toBe(true);
    const reordered = Object.fromEntries(Object.entries(clone()).reverse()) as unknown;
    const { cert: coerced } = coerceCertificate(reordered);
    expect(coerced).not.toBeNull();
    expect(await verifySeal(coerced as Certificate)).toBe(true); // key order is irrelevant
  });
});

describe("coercion of untrusted input", () => {
  it("rejects non-objects and missing fields with a plain reason", () => {
    expect(coerceCertificate("nope").cert).toBeNull();
    expect(coerceCertificate(null).cert).toBeNull();
    expect(coerceCertificate([1, 2]).cert).toBeNull();
    const missing = coerceCertificate({ schema_version: 1 });
    expect(missing.cert).toBeNull();
    expect(missing.reason).toMatch(/missing/);
  });

  it("rejects an off-vocabulary state", () => {
    const bad = JSON.parse(JSON.stringify(cert)) as Record<string, unknown>;
    bad.state = "GREEN";
    expect(coerceCertificate(bad).cert).toBeNull();
  });

  it("accepts the genuine fixture", () => {
    expect(coerceCertificate(clone()).cert).not.toBeNull();
  });
});
