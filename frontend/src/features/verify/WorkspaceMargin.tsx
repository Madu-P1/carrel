/**
 * The settled verdict layout (handoff §4, rebuilt 2026-07-04): a two-column
 * grid — the lawyer's draft as a serif read-back (left, Newsreader 19/2.05,
 * ≤68ch) beside the findings rail (right, worst-first vertical list). Each
 * treated sentence carries its tier's inline mark and a mono superscript claim
 * number; altered tokens inside a flagged sentence get the precise
 * danger-subtle mark (invariant 6 — mark the exact changed token, never a
 * refusal). Below the read-back, the dashed unplaced tray holds claims the
 * aligner could not pin (never guessed into the text).
 *
 * The four tiers must always read as different KINDS of thing (invariant 4):
 * pass = hairline underline (quiet; the absence of a problem), flag = solid
 * danger, assistive = dotted oxblood, refusal = ink double rule (the hero).
 * A `fuzzy` (approximate) placement renders distinctly from an `exact` one so
 * the loud mark never implies the tool found the lawyer's verbatim bytes.
 *
 * Pure presentation over the segmentation helpers. This replaced the findings
 * carousel (one-at-a-time) with the handoff's always-visible rail.
 */
import { useMemo } from "preact/hooks";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type ClaimDisposition } from "./claimDisposition";
import { displaySafe } from "./displaySafe";
import {
  highlightRuns,
  paragraphsFromSegments,
  segmentDraft,
  type ClaimSegment
} from "./documentSegments";
import styles from "./VerifyView.module.css";

/** The worst-first findings rail caps its rendered cards so a long document
 *  (hundreds of findings) cannot explode the DOM; the overflow is stated, not
 *  silently dropped, and every finding still lives in the read-back marks, the
 *  unplaced tray, and the certification exhibit. */
const RAIL_CAP = 50;

/** Map a disposition tier to the inline mark class on a claim span. */
function markClass(tier: ClaimDisposition["tier"]): string {
  switch (tier) {
    case "flag":
      return styles.markFlag;
    case "assistive":
      return styles.markAssistive;
    case "refusal":
      return styles.markRefusal;
    default:
      // Pass: the quiet hairline underline (handoff tier table). Not a badge,
      // not a color — the calibration mark that says "this one was checked".
      return styles.markPass;
  }
}

/** The rail-card tier attribute. A pass that carries an affirming detail (a
 *  contract "present"/verbatim confirmation, a verified citation) earns a card
 *  so the buyer can see what the engine actually vouched for — the calibration
 *  that tells them what a refusal means; a silent empty-detail pass stays off
 *  the rail (the absence of a flag is the pass). */
function noteTier(
  d: ClaimDisposition
): "flag" | "query" | "refusal" | "confirm" | null {
  if (d.tier === "flag") return "flag";
  if (d.tier === "assistive") return "query";
  if (d.tier === "refusal") return "refusal";
  if (d.tier === "pass" && d.detail.trim()) return "confirm";
  return null; // silent pass: no card
}

interface WorkspaceMarginProps {
  draftText: string;
  cards: VerifyClaimVerdict[];
  /** claim_index currently open in the Examination drawer, or null. */
  examined: number | null;
  onExamine: (claimIndex: number) => void;
}

interface ClaimMeta {
  card: VerifyClaimVerdict;
  disposition: ClaimDisposition;
}

export function WorkspaceMargin({
  draftText,
  cards,
  examined,
  onExamine
}: WorkspaceMarginProps) {
  // One memoized derivation for everything (draftText, cards) determines:
  // dispositions, segmentation, paragraph split, rail/tray sets, and the
  // display-safe text.
  const { metaByIndex, paragraphs, railClaims, trayClaims } = useMemo(() => {
    const meta = new Map<number, ClaimMeta>();
    cards.forEach((card, i) => {
      const idx = typeof card.claim_index === "number" ? card.claim_index : i;
      meta.set(idx, { card, disposition: dispositionForClaim(card) });
    });

    const segments = segmentDraft(draftText, cards);
    // Sanitize once here (displaySafe is 1-to-1, so spans stay aligned); the
    // render below ships the text to the DOM untouched.
    const safeParagraphs = paragraphsFromSegments(segments).map((para) =>
      para.map((seg) => ({ ...seg, text: displaySafe(seg.text) }))
    );

    // PLACED claims that carry a card, WORST-FIRST (handoff: the rail leads
    // with the flags, then the refusals, then the affirmed passes).
    const placedClaimIndices = segments
      .filter((s): s is ClaimSegment => s.kind === "claim")
      .map((s) => s.claimIndex);
    const rail = placedClaimIndices
      .filter((idx) => {
        const m = meta.get(idx);
        return m ? noteTier(m.disposition) !== null : false;
      })
      .sort(
        (a, b) =>
          DISPOSITION_ORDER[meta.get(a)!.disposition.kind] -
          DISPOSITION_ORDER[meta.get(b)!.disposition.kind]
      );

    // Unplaced claims (no span produced) -> the tray, worst-first.
    const placedSet = new Set(placedClaimIndices);
    const tray = cards
      .map((card, i) => (typeof card.claim_index === "number" ? card.claim_index : i))
      .filter((idx) => !placedSet.has(idx))
      .map((idx) => meta.get(idx)!)
      .filter(Boolean)
      .sort((a, b) => DISPOSITION_ORDER[a.disposition.kind] - DISPOSITION_ORDER[b.disposition.kind]);

    return { metaByIndex: meta, paragraphs: safeParagraphs, railClaims: rail, trayClaims: tray };
  }, [draftText, cards]);

  const hasTray = trayClaims.length > 0;

  return (
    <div className={styles.settledGrid}>
      <article className={styles.readback}>
        <div className={styles.colEyebrow}>Draft · read-back</div>
        {paragraphs.map((para, pi) => (
          <p key={pi} className={styles.docParagraph}>
            {para.map((seg, si) =>
              seg.kind === "text" ? (
                <span key={si}>{seg.text}</span>
              ) : (
                <ClaimMark
                  key={si}
                  segment={seg}
                  meta={metaByIndex.get(seg.claimIndex)}
                  isExamined={examined === seg.claimIndex}
                  onExamine={onExamine}
                />
              )
            )}
          </p>
        ))}

        {hasTray ? <UnplacedTray claims={trayClaims} onExamine={onExamine} /> : null}
      </article>

      <aside className={styles.findingsRail} aria-label="Findings, worst first">
        <div className={styles.colEyebrow}>Findings · worst first</div>
        {railClaims.slice(0, RAIL_CAP).map((idx) => {
          const meta = metaByIndex.get(idx);
          if (!meta) return null;
          return (
            <FindingCard
              key={idx}
              claimIndex={idx}
              disposition={meta.disposition}
              card={meta.card}
              onExamine={onExamine}
            />
          );
        })}
        {railClaims.length > RAIL_CAP ? (
          // No silent cap (long-doc UX): a long document can raise hundreds of
          // findings; the rail shows the worst RAIL_CAP, but says so and points
          // to where every finding is kept. The rest are NOT dropped from the
          // record — they are in the read-back marks, the tray, and the exhibit.
          <p className={styles.noteDetail} data-rail-capped={railClaims.length}>
            Showing the worst {RAIL_CAP} of {railClaims.length} findings. Every finding is marked in
            the read-back and listed in the certification exhibit.
          </p>
        ) : null}
        {railClaims.length === 0 ? (
          <p className={styles.noteDetail}>
            No findings to raise. Every treated statement is marked in the draft.
          </p>
        ) : null}
      </aside>
    </div>
  );
}

function ClaimMark({
  segment,
  meta,
  isExamined,
  onExamine
}: {
  segment: ClaimSegment;
  meta: ClaimMeta | undefined;
  isExamined: boolean;
  onExamine: (claimIndex: number) => void;
}) {
  const tier = meta?.disposition.tier ?? "pass";
  const label = meta?.disposition.label ?? "";
  // Exact-token highlight: a flagged statement underlines the precise verbatim
  // span(s) the engine found in contradiction with the source (e.g. the altered
  // figure "60 billion"), so the eye lands on the changed token, not just the
  // sentence. Only on a flag; only verbatim substrings (highlightRuns drops any
  // span not literally present), so a near-miss never paints the wrong word.
  const flaggedSpans = tier === "flag" ? (meta?.card.flagged_spans ?? []) : [];
  const runs = flaggedSpans.length > 0 ? highlightRuns(segment.text, flaggedSpans) : null;
  const interactive = tier !== "pass" || Boolean(meta);
  const fuzzy = segment.method === "fuzzy";
  // The announcement must keep the visible register split: only a real flag is
  // "flagged"; the refusal is a could-not-check, and an assistive note is a
  // query for review. A screen reader that hears "flagged" for an honest
  // refusal has been handed an accusation the engine never made.
  const fuzzyNote = fuzzy && tier !== "pass" ? ", placement approximate" : "";
  const aria =
    tier === "pass"
      ? `Statement, checked and supported: ${segment.text}`
      : tier === "refusal"
        ? `Statement could not be checked, ${label}${fuzzyNote}: ${segment.text}`
        : tier === "assistive"
          ? `Statement noted for your review, ${label}${fuzzyNote}: ${segment.text}`
          : `Statement flagged ${label}${fuzzyNote}: ${segment.text}`;
  return (
    <span
      className={[
        styles.claimMark,
        markClass(tier),
        fuzzy && tier !== "pass" ? styles.markFuzzy : "",
        isExamined ? styles.claimMarkExamined : ""
      ]
        .filter(Boolean)
        .join(" ")}
      data-claim-index={segment.claimIndex}
      data-tier={tier}
      role={interactive ? "button" : undefined}
      tabIndex={interactive ? 0 : undefined}
      aria-label={aria}
      onClick={interactive ? () => onExamine(segment.claimIndex) : undefined}
      onKeyDown={
        interactive
          ? (e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onExamine(segment.claimIndex);
              }
            }
          : undefined
      }
    >
      {runs
        ? runs.map((run, ri) =>
            run.flagged ? (
              <mark key={ri} className={styles.markToken}>
                {run.text}
              </mark>
            ) : (
              <span key={ri}>{run.text}</span>
            )
          )
        : segment.text}
      {/* The mono superscript claim number (handoff §4): the eye's link from a
          marked sentence to its rail card and examination. aria-hidden — the
          span's own label already names the claim. */}
      <sup className={styles.claimMarker} data-tier={tier} aria-hidden="true">
        {segment.claimIndex + 1}
      </sup>
    </span>
  );
}

/** One findings-rail card (handoff §4): mono tier label under the tier's top
 *  rule, the claim as the title line, the disposition detail beneath. */
function FindingCard({
  claimIndex,
  disposition,
  card,
  onExamine
}: {
  claimIndex: number;
  disposition: ClaimDisposition;
  card: VerifyClaimVerdict;
  onExamine: (claimIndex: number) => void;
}) {
  // The wire's unsupported_reason is the refusal's audit trail, but for an
  // unknown-verdict card the disposition detail already IS that reason
  // (claimDisposition reads it first); suppress the trail when it would print
  // the identical sentence twice in one card.
  const trail =
    card.unsupported_reason &&
    disposition.tier === "refusal" &&
    card.unsupported_reason !== disposition.detail
      ? card.unsupported_reason
      : null;
  return (
    <button
      type="button"
      className={styles.findingCard}
      data-tier={disposition.tier}
      data-note-key={claimIndex}
      onClick={() => onExamine(claimIndex)}
    >
      <span className={styles.findingLabel}>
        {disposition.label}
        {disposition.tier === "assistive" ? (
          <span className={styles.findingTag}>ASSISTIVE</span>
        ) : null}
      </span>
      {card.claim_text ? (
        <span className={styles.findingTitle}>{displaySafe(card.claim_text)}</span>
      ) : null}
      {disposition.detail ? (
        <span className={styles.findingDetail}>{disposition.detail}</span>
      ) : null}
      {trail ? <span className={styles.findingDetail}>{trail}</span> : null}
    </button>
  );
}

function UnplacedTray({
  claims,
  onExamine
}: {
  claims: ClaimMeta[];
  onExamine: (claimIndex: number) => void;
}) {
  return (
    <section className={styles.unplacedTray} aria-label="Statements not located in the draft text">
      <h2 className={styles.trayLabel}>
        Could not pin to the text · {claims.length === 1 ? "1 claim" : `${claims.length} claims`}
      </h2>
      <p className={styles.trayNote}>
        These statements were checked, but their exact wording could not be matched to a span in the
        draft above. Review them here.
      </p>
      <ul className={styles.trayList}>
        {claims.map((m) => {
          const idx = m.card.claim_index ?? 0;
          return (
            <li key={idx}>
              <button
                type="button"
                className={styles.trayRow}
                onClick={() => onExamine(idx as number)}
                data-tier={m.disposition.tier}
              >
                <span className={styles.trayIndex}>{String(idx).padStart(2, "0")}</span>
                <span className={styles.trayBody}>
                  <span className={styles.trayDisp}>{m.disposition.label}</span>
                  <span className={styles.trayClaim}>{m.card.claim_text}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </section>
  );
}
