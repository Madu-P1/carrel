import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import companionCert from "./__fixtures__/companion-issued-cert.json";
import docDraftCert from "./__fixtures__/document-draft-cert.json";
import specimenCert from "./__fixtures__/specimen-cert.json";
import { canonicalJson, coerceCertificate, sha256Hex } from "./certificate";

/**
 * The standalone verifier (verifier/index.html) is the free, dependency-less
 * public seal-checker — the demand-side artifact anyone can host or open from
 * disk. Its inlined algorithm must stay byte-identical in behavior to the
 * kernel contract this app's certificate.ts already pins against
 * kernel-issued fixtures. This suite extracts the HTML's own functions and
 * proves them against the same fixtures, so the page can never silently
 * drift: a green here means a certificate sealed by ANY Cachet surface
 * verifies identically in the standalone page.
 */

const html = readFileSync(resolve(__dirname, "../../../../verifier/index.html"), "utf8");

/** Pull one top-level `function name(...) {...}` declaration out of the page's
 *  script by brace counting (regex-to-first-`}` breaks on nested braces). */
function extractFunction(name: string): string {
  let start = html.indexOf(`function ${name}`);
  expect(start, `verifier/index.html must define function ${name}`).toBeGreaterThan(-1);
  // An `async function` declaration must keep its async keyword, or the
  // extracted body's await becomes a syntax error.
  if (html.slice(Math.max(0, start - 6), start) === "async ") start -= 6;
  const open = html.indexOf("{", start);
  let depth = 0;
  for (let i = open; i < html.length; i++) {
    if (html[i] === "{") depth++;
    else if (html[i] === "}") {
      depth--;
      if (depth === 0) return html.slice(start, i + 1);
    }
  }
  throw new Error(`unbalanced braces extracting ${name}`);
}

type CanonicalJson = (value: unknown) => string;

function standaloneCanonicalJson(): CanonicalJson {
  const src = extractFunction("canonicalJson");
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  return new Function(`${src}; return canonicalJson;`)() as CanonicalJson;
}

type Sha256Hex = (text: string) => Promise<string>;
type Coerce = (raw: unknown) => { cert: unknown; reason: string };

function standaloneSha256Hex(): Sha256Hex {
  const src = extractFunction("sha256Hex");
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  return new Function(`${src}; return sha256Hex;`)() as Sha256Hex;
}

function standaloneCoerce(): Coerce {
  // coerce depends on the page's own VALID_STATES/REQUIRED constants; extract
  // them alongside so the function closes over the page's real definitions.
  const constants = html.match(/const VALID_STATES = [^;]+;\s*const REQUIRED = [^;]+;/);
  expect(constants, "verifier must define VALID_STATES and REQUIRED").not.toBeNull();
  const src = extractFunction("coerce");
  // eslint-disable-next-line @typescript-eslint/no-implied-eval
  return new Function(`${constants![0]}; ${src}; return coerce;`)() as Coerce;
}

async function standaloneFingerprint(cert: Record<string, unknown>): Promise<string> {
  const canonical = standaloneCanonicalJson();
  const digest = standaloneSha256Hex();
  const body: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(cert)) if (k !== "fingerprint") body[k] = v;
  // The page's OWN digest, so a broken hex conversion cannot hide behind the
  // app's implementation.
  return digest(canonical(body));
}

describe("the standalone verifier page matches the kernel contract", () => {
  it("canonicalizes byte-identically to the app's certificate.ts", () => {
    const standalone = standaloneCanonicalJson();
    for (const fixture of [specimenCert, companionCert]) {
      expect(standalone(fixture)).toBe(canonicalJson(fixture));
    }
    // The separator/sorting edge shapes the contract names explicitly.
    expect(standalone({ b: 1, a: ["x", { d: null, c: true }] })).toBe(
      '{"a":["x",{"c":true,"d":null}],"b":1}'
    );
  });

  it("verifies kernel-issued fixtures as intact", async () => {
    for (const fixture of [specimenCert, companionCert]) {
      const cert = fixture as unknown as Record<string, unknown>;
      expect(await standaloneFingerprint(cert)).toBe(cert.fingerprint);
    }
  });

  it("breaks the seal on any single-field tamper", async () => {
    const cert = JSON.parse(JSON.stringify(specimenCert)) as {
      claims: Array<{ state: string }>;
      issued_at: string;
      fingerprint: string;
    };
    cert.claims[0].state = cert.claims[0].state === "altered" ? "verified" : "altered";
    expect(await standaloneFingerprint(cert as unknown as Record<string, unknown>)).not.toBe(
      cert.fingerprint
    );
  });

  it("hex-encodes digests identically to the app (incl. low bytes needing padStart)", async () => {
    const digest = standaloneSha256Hex();
    // "c" hashes to 2e7d2c03...: a leading low nibble exercises padStart.
    for (const vector of ["c", "", "cachet", "µ unicode ünïcode"]) {
      expect(await digest(vector)).toBe(await sha256Hex(vector));
    }
  });

  it("coerces structurally like the app, same reasons included", () => {
    const coerce = standaloneCoerce();
    // Non-object and bad shapes.
    for (const bad of [null, 42, [], "x"]) {
      const ours = coerceCertificate(bad);
      const theirs = coerce(bad);
      expect(Boolean(theirs.cert)).toBe(Boolean(ours.cert));
      expect(theirs.reason).toBe(ours.reason);
    }
    // Each required field missing, one at a time.
    for (const key of Object.keys(specimenCert)) {
      const clipped = { ...(specimenCert as Record<string, unknown>) };
      delete clipped[key];
      const ours = coerceCertificate(clipped);
      const theirs = coerce(clipped);
      expect(Boolean(theirs.cert), `field ${key}`).toBe(Boolean(ours.cert));
      expect(theirs.reason, `field ${key}`).toBe(ours.reason);
    }
    // A state outside the three-verdict vocabulary.
    const badState = { ...(specimenCert as Record<string, unknown>), state: "probably_fine" };
    expect(coerce(badState).reason).toBe(coerceCertificate(badState).reason);
  });

  it("verifies a document-draft provenance cert intact and renders the file line (D2)", async () => {
    const cert = docDraftCert as unknown as Record<string, unknown>;
    // The two additive fields ride inside the sealed body, so the page's own
    // digest still verifies the kernel-issued provenance cert intact.
    expect(await standaloneFingerprint(cert)).toBe(cert.fingerprint);
    // And the page names the original file (additive render, present-only).
    expect(html).toContain("Draft file");
    expect(html).toContain("cert.draft_file_sha256");
    expect(html).toContain("cert.draft_extractor");
  });

  it("keeps the page self-contained: no external requests, no telemetry", () => {
    // The whole point of the artifact: verifying a certificate must cost the
    // demander nothing and leak nothing. One file, zero network.
    expect(html).not.toMatch(/https?:\/\//i);
    expect(html).not.toMatch(/<script[^>]+src=/i);
    expect(html).not.toMatch(/<link[^>]+href=/i);
    expect(html).not.toMatch(/\bfetch\s*\(|XMLHttpRequest|navigator\.sendBeacon/);
    // And it states the equal-weight rule (invariant 7) to the demander.
    expect(html).toContain("same weight as confirmations");
  });
});
