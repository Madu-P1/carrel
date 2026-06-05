/**
 * Carrel V2 verify surface, certification artifact model.
 *
 * Builds the dated, fingerprinted exhibit a litigator keeps in the file: it is
 * the saleable object, because willingness-to-pay concentrates on defensibility
 * (a contemporaneous record that the check happened, what it found, and what it
 * could NOT confirm), not on the checking itself. The "items requiring attorney
 * review" set is the headline; a wall of green checks is not.
 *
 * Pure and deterministic given (response, generatedAtISO). No confidence
 * numbers anywhere, by design.
 */
import type { VerifyClaimVerdict, VerifyResponse } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type DispositionKind } from "./claimDisposition";

/**
 * SHA-256 content fingerprint of the checked draft, as 64-char lowercase hex.
 * Not a cryptographic protocol (no key, no signature); a collision-resistant,
 * stable marker that ties the certification to the exact text that was checked,
 * so the seal cannot be silently re-attached to a different draft. Computed
 * synchronously over the UTF-8 bytes so buildCertification stays pure and
 * synchronous; the platform's only native SHA-256 (crypto.subtle) is async,
 * which would force this and its render call site into a Promise.
 */
export function fingerprintDraft(text: string): string {
  return sha256Hex(new TextEncoder().encode(text));
}

const SHA256_K = new Uint32Array([
  0x428a2f98, 0x71374491, 0xb5c0fbcf, 0xe9b5dba5, 0x3956c25b, 0x59f111f1, 0x923f82a4, 0xab1c5ed5,
  0xd807aa98, 0x12835b01, 0x243185be, 0x550c7dc3, 0x72be5d74, 0x80deb1fe, 0x9bdc06a7, 0xc19bf174,
  0xe49b69c1, 0xefbe4786, 0x0fc19dc6, 0x240ca1cc, 0x2de92c6f, 0x4a7484aa, 0x5cb0a9dc, 0x76f988da,
  0x983e5152, 0xa831c66d, 0xb00327c8, 0xbf597fc7, 0xc6e00bf3, 0xd5a79147, 0x06ca6351, 0x14292967,
  0x27b70a85, 0x2e1b2138, 0x4d2c6dfc, 0x53380d13, 0x650a7354, 0x766a0abb, 0x81c2c92e, 0x92722c85,
  0xa2bfe8a1, 0xa81a664b, 0xc24b8b70, 0xc76c51a3, 0xd192e819, 0xd6990624, 0xf40e3585, 0x106aa070,
  0x19a4c116, 0x1e376c08, 0x2748774c, 0x34b0bcb5, 0x391c0cb3, 0x4ed8aa4a, 0x5b9cca4f, 0x682e6ff3,
  0x748f82ee, 0x78a5636f, 0x84c87814, 0x8cc70208, 0x90befffa, 0xa4506ceb, 0xbef9a3f7, 0xc67178f2
]);

const rotr = (x: number, n: number): number => (x >>> n) | (x << (32 - n));

/**
 * Minimal dependency-free synchronous SHA-256 (FIPS 180-4) over a byte array,
 * returning 64-char lowercase hex. Local so the fingerprint stays sync; the
 * known-answer vectors in certification.test.ts lock its correctness.
 */
function sha256Hex(bytes: Uint8Array): string {
  const h = new Uint32Array([
    0x6a09e667, 0xbb67ae85, 0x3c6ef372, 0xa54ff53a, 0x510e527f, 0x9b05688c, 0x1f83d9ab, 0x5be0cd19
  ]);

  // Pad to a multiple of 64 bytes: 0x80, zeros, then the 64-bit big-endian bit length.
  const bitLen = bytes.length * 8;
  const paddedLen = ((((bytes.length + 8) >> 6) + 1) << 6);
  const msg = new Uint8Array(paddedLen);
  msg.set(bytes);
  msg[bytes.length] = 0x80;
  const dv = new DataView(msg.buffer);
  dv.setUint32(paddedLen - 8, Math.floor(bitLen / 0x100000000), false);
  dv.setUint32(paddedLen - 4, bitLen >>> 0, false);

  const w = new Uint32Array(64);
  for (let off = 0; off < paddedLen; off += 64) {
    for (let i = 0; i < 16; i += 1) w[i] = dv.getUint32(off + i * 4, false);
    for (let i = 16; i < 64; i += 1) {
      const s0 = rotr(w[i - 15], 7) ^ rotr(w[i - 15], 18) ^ (w[i - 15] >>> 3);
      const s1 = rotr(w[i - 2], 17) ^ rotr(w[i - 2], 19) ^ (w[i - 2] >>> 10);
      w[i] = w[i - 16] + s0 + w[i - 7] + s1;
    }
    let [a, b, c, d, e, f, g, hh] = h;
    for (let i = 0; i < 64; i += 1) {
      const t1 = hh + (rotr(e, 6) ^ rotr(e, 11) ^ rotr(e, 25)) + ((e & f) ^ (~e & g)) + SHA256_K[i] + w[i];
      const t2 = (rotr(a, 2) ^ rotr(a, 13) ^ rotr(a, 22)) + ((a & b) ^ (a & c) ^ (b & c));
      hh = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
    }
    h[0] += a; h[1] += b; h[2] += c; h[3] += d; h[4] += e; h[5] += f; h[6] += g; h[7] += hh;
  }

  let hex = "";
  for (let i = 0; i < 8; i += 1) hex += h[i].toString(16).padStart(8, "0");
  return hex;
}

export type SealState = "unsealed" | "sealed" | "cracked";

/**
 * Seal state from a pure string comparison of two draft fingerprints: the one
 * captured when the human set the seal and the current draft's. No seal yet is
 * "unsealed"; a seal whose captured fingerprint still matches is "sealed"; a
 * seal whose draft has since changed is "cracked" (stale, shown dimmed and
 * never alarmed). No hashing at compare time.
 */
export function sealStateFor(
  sealedFingerprint: string | null,
  currentFingerprint: string
): SealState {
  if (sealedFingerprint === null) return "unsealed";
  return sealedFingerprint === currentFingerprint ? "sealed" : "cracked";
}

/** SHA-256 (64-char hex) of UTF-8 text. Same primitive as the draft fingerprint. */
export function sha256OfText(text: string): string {
  return sha256Hex(new TextEncoder().encode(text));
}

const LOCAL_PROVIDERS = new Set(["afm", "ollama", "deterministic"]);

/** True when the producing provider ran on-device (no data left the machine). */
export function isLocalExecution(provider: string): boolean {
  return LOCAL_PROVIDERS.has((provider ?? "").trim().toLowerCase());
}

/**
 * The named "no data left this device" attestation, honest about cloud vs local.
 * For a cloud provider it states plainly that the draft and sources were sent out,
 * so the artifact never implies a local guarantee it cannot make.
 */
export function attestationFor(provider: string): string {
  if (isLocalExecution(provider)) {
    return "No data left this device. All verification ran locally against the documents you loaded.";
  }
  const named = (provider ?? "").trim() || "a cloud model";
  return `Verification ran via ${named} in the cloud. The draft and the sources it was checked against were sent to that provider.`;
}

export interface CertificationItem {
  /** 1-based display index in original draft order. */
  index: number;
  kind: DispositionKind;
  label: string;
  claimText: string;
  /** Document names / case citations the statement was checked against. */
  sources: string[];
  /** SHA-256 of each checked source's content, same order as `sources`. */
  sourceFingerprints: string[];
}

export interface CertificationModel {
  generatedAtISO: string;
  fingerprint: string;
  provider: string;
  /** Whether the producing provider ran on-device. */
  localExecution: boolean;
  /** The named "no data left this device" attestation (honest cloud vs local). */
  attestation: string;
  totalStatements: number;
  needsReviewCount: number;
  counts: Record<DispositionKind, number>;
  /** The not-confirmed set (everything that is not "supported"), worst-first. */
  flagged: CertificationItem[];
  allItems: CertificationItem[];
}

function sourcesFor(card: VerifyClaimVerdict): string[] {
  const out: string[] = [];
  for (const c of card.citations ?? []) {
    const name = c.document_name || c.document_id || "source";
    out.push(c.page_num ? `${name}, p. ${c.page_num}` : String(name));
  }
  for (const batch of card.case_verdicts ?? []) {
    if (!batch?.ok) continue;
    for (const v of batch.verdicts ?? []) {
      out.push(v.case_name ? `${v.case_name} (${v.citation})` : v.citation);
    }
  }
  return out;
}

/** Per-source SHA-256, aligned with sourcesFor: the cited content where present,
 * otherwise the citation string. Proves which exact source text was checked. */
function sourceFingerprintsFor(card: VerifyClaimVerdict): string[] {
  const out: string[] = [];
  for (const c of card.citations ?? []) {
    const content = (c as { content?: string }).content;
    out.push(sha256OfText(typeof content === "string" && content ? content : ""));
  }
  for (const batch of card.case_verdicts ?? []) {
    if (!batch?.ok) continue;
    for (const v of batch.verdicts ?? []) {
      out.push(sha256OfText(v.citation));
    }
  }
  return out;
}

/** Machine-readable export: the full certification model plus a schema version. */
export function certificationToJson(model: CertificationModel): string {
  return JSON.stringify({ schema_version: 1, ...model }, null, 2);
}

export function buildCertification(
  response: VerifyResponse,
  generatedAtISO: string
): CertificationModel {
  const cards = (response.claim_verdicts ?? []) as VerifyClaimVerdict[];
  const counts: Record<DispositionKind, number> = {
    supported: 0,
    citation_not_found: 0,
    proposition_unsupported: 0,
    claim_unsupported: 0,
    could_not_check: 0
  };
  const allItems: CertificationItem[] = cards.map((card, i) => {
    const d = dispositionForClaim(card);
    counts[d.kind] += 1;
    return {
      index: i + 1,
      kind: d.kind,
      label: d.label,
      claimText: card.claim_text ?? "",
      sources: sourcesFor(card),
      sourceFingerprints: sourceFingerprintsFor(card)
    };
  });
  const flagged = allItems
    .filter((it) => it.kind !== "supported")
    .sort((a, b) => DISPOSITION_ORDER[a.kind] - DISPOSITION_ORDER[b.kind]);
  const provider = response.provider ?? "";
  return {
    generatedAtISO,
    fingerprint: fingerprintDraft(response.draft_text ?? ""),
    provider,
    localExecution: isLocalExecution(provider),
    attestation: attestationFor(provider),
    totalStatements: allItems.length,
    needsReviewCount: flagged.length,
    counts,
    flagged,
    allItems
  };
}
