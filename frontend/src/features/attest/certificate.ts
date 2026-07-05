/**
 * The sealed attestation certificate, verified IN THE BROWSER.
 *
 * This is the frontend twin of `cachet_verify/certificate.py` and the
 * connective tissue of the whole product: the app, the loopback daemon, the
 * CLI, and the companion all issue the SAME canonical record, so any surface
 * (or any third party) can hand a certificate to this code and learn, offline,
 * whether the seal is intact. No network, no backend: canonical JSON plus
 * SHA-256 via Web Crypto.
 *
 * Canonicalization contract (must match the Python kernel byte-for-byte, and
 * is pinned against a kernel-issued fixture in certificate.test.ts): keys
 * sorted, separators `,` and `:` with no whitespace, UTF-8 (no ASCII
 * escaping). Certificates carry only strings and integers, so number
 * formatting cannot diverge between the two implementations.
 */

export type VerdictState = "verified" | "altered" | "could_not_check";

export interface CertCheck {
  state: VerdictState;
  provenance: string;
  detail: string;
  subject: string;
}

export interface CertClaim {
  claim: string;
  state: VerdictState;
  checks: CertCheck[];
}

export interface Certificate {
  schema_version: number;
  kernel_version: string;
  issued_at: string;
  draft_sha256: string;
  source_sha256s: string[];
  state: VerdictState;
  claims: CertClaim[];
  fingerprint: string;
  /** Present only when the draft came from an uploaded DOCUMENT: the sha256 of
   *  the ORIGINAL file bytes (draft_sha256 stays the extracted-text hash). */
  draft_file_sha256?: string;
  /** The extraction identity (e.g. "pdf:native_text", "pdf:docling-rapidocr"
   *  for OCR). Both fields are additive and ride inside the sealed body, so an
   *  edit to either breaks the seal like any other tamper. */
  draft_extractor?: string;
}

const VALID_STATES: ReadonlySet<string> = new Set(["verified", "altered", "could_not_check"]);

/** Structural check: is this object shaped like a certificate at all?
 *  Returns a plain-language reason when it is not (shown to the user). */
export function coerceCertificate(raw: unknown): { cert: Certificate | null; reason: string } {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) {
    return { cert: null, reason: "Not a certificate: expected a JSON object." };
  }
  const record = raw as Record<string, unknown>;
  for (const key of [
    "schema_version",
    "issued_at",
    "draft_sha256",
    "source_sha256s",
    "state",
    "claims",
    "fingerprint",
  ]) {
    if (!(key in record)) {
      return { cert: null, reason: `Not a certificate: the ${key} field is missing.` };
    }
  }
  if (typeof record.state !== "string" || !VALID_STATES.has(record.state)) {
    return { cert: null, reason: "Not a certificate: the state is not a Cachet verdict." };
  }
  if (!Array.isArray(record.claims)) {
    return { cert: null, reason: "Not a certificate: claims is not a list." };
  }
  return { cert: record as unknown as Certificate, reason: "" };
}

/** Byte-stable serialization matching Python's
 *  json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False). */
export function canonicalJson(value: unknown): string {
  if (value === null || typeof value === "number" || typeof value === "boolean") {
    return JSON.stringify(value);
  }
  if (typeof value === "string") {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    return `[${value.map(canonicalJson).join(",")}]`;
  }
  const record = value as Record<string, unknown>;
  const keys = Object.keys(record).sort();
  const parts = keys.map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`);
  return `{${parts.join(",")}}`;
}

export async function sha256Hex(text: string): Promise<string> {
  const bytes = new TextEncoder().encode(text);
  const digest = await globalThis.crypto.subtle.digest("SHA-256", bytes);
  return Array.from(new Uint8Array(digest))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

/** Is the seal intact? Recomputes the SHA-256 of the canonical body (every
 *  field except the fingerprint) and compares. Any post-issuance tampering,
 *  one flipped verdict, one edited detail, breaks it. */
export async function verifySeal(cert: Certificate): Promise<boolean> {
  const body: Record<string, unknown> = {};
  for (const [key, value] of Object.entries(cert)) {
    if (key !== "fingerprint") body[key] = value;
  }
  return (await sha256Hex(canonicalJson(body))) === cert.fingerprint;
}

export interface CertSummary {
  total: number;
  verified: number;
  altered: number;
  couldNotCheck: number;
}

export function summarizeCertificate(cert: Certificate): CertSummary {
  const summary: CertSummary = { total: 0, verified: 0, altered: 0, couldNotCheck: 0 };
  for (const claim of cert.claims ?? []) {
    summary.total += 1;
    if (claim.state === "verified") summary.verified += 1;
    else if (claim.state === "altered") summary.altered += 1;
    else summary.couldNotCheck += 1;
  }
  return summary;
}
