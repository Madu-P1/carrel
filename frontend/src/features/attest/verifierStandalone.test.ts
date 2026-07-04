import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import companionCert from "./__fixtures__/companion-issued-cert.json";
import specimenCert from "./__fixtures__/specimen-cert.json";
import { canonicalJson, sha256Hex } from "./certificate";

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
  const start = html.indexOf(`function ${name}`);
  expect(start, `verifier/index.html must define function ${name}`).toBeGreaterThan(-1);
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

async function standaloneFingerprint(cert: Record<string, unknown>): Promise<string> {
  const canonical = standaloneCanonicalJson();
  const body: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(cert)) if (k !== "fingerprint") body[k] = v;
  // sha256Hex is pure WebCrypto in both implementations; reuse the app's.
  return sha256Hex(canonical(body));
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
