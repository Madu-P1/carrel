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
 * FNV-1a 32-bit content fingerprint of the checked draft. Not cryptographic; a
 * stable marker that ties the certification to the exact text that was checked,
 * so the report cannot be silently attached to a different draft. Can be
 * upgraded to a SHA-256 digest later without changing the model shape.
 */
export function fingerprintDraft(text: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = Math.imul(h, 0x01000193);
  }
  return (h >>> 0).toString(16).padStart(8, "0");
}

export interface CertificationItem {
  /** 1-based display index in original draft order. */
  index: number;
  kind: DispositionKind;
  label: string;
  claimText: string;
  /** Document names / case citations the statement was checked against. */
  sources: string[];
}

export interface CertificationModel {
  generatedAtISO: string;
  fingerprint: string;
  provider: string;
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
      sources: sourcesFor(card)
    };
  });
  const flagged = allItems
    .filter((it) => it.kind !== "supported")
    .sort((a, b) => DISPOSITION_ORDER[a.kind] - DISPOSITION_ORDER[b.kind]);
  return {
    generatedAtISO,
    fingerprint: fingerprintDraft(response.draft_text ?? ""),
    provider: response.provider ?? "",
    totalStatements: allItems.length,
    needsReviewCount: flagged.length,
    counts,
    flagged,
    allItems
  };
}
