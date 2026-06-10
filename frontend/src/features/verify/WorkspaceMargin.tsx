/**
 * Cachet PR5b (Direction A, document-primary) — the Workspace / Margin layout.
 *
 * Renders the lawyer's draft as a cold read-back record on warm paper: the
 * document body (left) with each placed claim inline-marked at its span, the
 * 300px right rail holding one disposition note per non-supported placed claim
 * pinned at its eye-line, and the unplaced tray below for claims the aligner
 * could not pin (PR5a never mis-pins; an un-placeable claim is surfaced here,
 * never guessed into the margin).
 *
 * Supported claims are UNMARKED. The absence of a mark is the pass; there is no
 * green and no VERIFIED badge, by design. Deterministic flags wear the single
 * oxblood accent; an assistive holding-match judgment wears a quiet dotted
 * pencil, never oxblood; the refusal wears a composed ink bracket. A `fuzzy`
 * (approximate) placement is rendered distinctly from an `exact` one so the loud
 * mark never implies the tool found the lawyer's verbatim bytes when it matched
 * a near-identical span.
 *
 * Pure presentation over PR5a/PR4 data + the segmentation/rail-layout helpers.
 * Motion (ink-in choreography, claim pulse) is deferred to the operator visual
 * gate; this slice ships structure + functional transitions only.
 */
import { useLayoutEffect, useMemo, useRef, useState } from "preact/hooks";

import type { VerifyClaimVerdict } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type ClaimDisposition } from "./claimDisposition";
import { displaySafe } from "./displaySafe";
import {
  paragraphsFromSegments,
  segmentDraft,
  type ClaimSegment
} from "./documentSegments";
import { layoutRail, type RailAnchor, type RailPlacement } from "./railLayout";
import styles from "./VerifyView.module.css";

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
      return ""; // pass: unmarked
  }
}

/** The rail-note tier attribute (flag/query/refusal) for the left border. */
function noteTier(tier: ClaimDisposition["tier"]): "flag" | "query" | "refusal" | null {
  if (tier === "flag") return "flag";
  if (tier === "assistive") return "query";
  if (tier === "refusal") return "refusal";
  return null; // pass: no note
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
  // display-safe text. This render re-runs on every selection change
  // (`examined`), and recomputing dispositionForClaim per card three times
  // plus sanitizing the whole document each time was the measurable hot path
  // on long drafts.
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

    // Non-supported PLACED claims get a rail note. (Supported = unmarked, no
    // note. Unplaced = no span here, lives in the tray.)
    const placedClaimIndices = segments
      .filter((s): s is ClaimSegment => s.kind === "claim")
      .map((s) => s.claimIndex);
    const rail = placedClaimIndices.filter((idx) => {
      const m = meta.get(idx);
      return m ? noteTier(m.disposition.tier) !== null : false;
    });

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

  // --- rail vertical pinning (measured; collision math is the pure layoutRail) ---
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const railRef = useRef<HTMLDivElement | null>(null);
  const [placements, setPlacements] = useState<RailPlacement[]>([]);
  // Stable dependency key: the effect only needs to re-measure when the SET of
  // rail claims (or the draft / open drawer) changes, not on every render.
  const railKey = railClaims.join(",");

  useLayoutEffect(() => {
    const body = bodyRef.current;
    const rail = railRef.current;
    if (!body || !rail) return;
    const railTop = rail.getBoundingClientRect().top;
    const noteEls = Array.from(rail.querySelectorAll<HTMLElement>("[data-note-key]"));
    const anchors: RailAnchor[] = [];
    for (const idx of railKey ? railKey.split(",").map(Number) : []) {
      const mark = body.querySelector<HTMLElement>(`[data-claim-index="${idx}"]`);
      const noteEl = noteEls.find((n) => n.dataset.noteKey === String(idx));
      if (!mark || !noteEl) continue;
      anchors.push({
        key: idx,
        desiredTop: mark.getBoundingClientRect().top - railTop,
        height: noteEl.getBoundingClientRect().height
      });
    }
    setPlacements(layoutRail(anchors));
    // Re-run when the set of rail claims, the draft, or the open drawer changes.
  }, [draftText, railKey, examined]);

  const topFor = (idx: number): number | undefined =>
    placements.find((p) => p.key === idx)?.top;

  const hasTray = trayClaims.length > 0;

  return (
    <div className={styles.canvas}>
      <div className={styles.documentBody} ref={bodyRef}>
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
      </div>

      <div className={styles.rail} ref={railRef} aria-label="Margin findings">
        {railClaims.map((idx) => {
          const meta = metaByIndex.get(idx);
          if (!meta) return null;
          return (
            <MarginNote
              key={idx}
              claimIndex={idx}
              disposition={meta.disposition}
              card={meta.card}
              top={topFor(idx)}
              onExamine={onExamine}
            />
          );
        })}
      </div>

      {hasTray ? (
        <UnplacedTray
          claims={trayClaims}
          onExamine={onExamine}
        />
      ) : null}
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
  // Supported (pass): a plain, tabbable span that announces "checked, supported"
  // but carries no visible mark. Flags/assistive/refusal carry their mark.
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
      {segment.text}
    </span>
  );
}

function MarginNote({
  claimIndex,
  disposition,
  card,
  top,
  onExamine
}: {
  claimIndex: number;
  disposition: ClaimDisposition;
  card: VerifyClaimVerdict;
  top: number | undefined;
  onExamine: (claimIndex: number) => void;
}) {
  const tier = noteTier(disposition.tier);
  // The wire's unsupported_reason is the refusal's audit trail, but for an
  // unknown-verdict card the disposition detail already IS that reason
  // (claimDisposition reads it first); suppress the trail when it would print
  // the identical sentence twice in one note.
  const trail =
    card.unsupported_reason && tier === "refusal" && card.unsupported_reason !== disposition.detail
      ? card.unsupported_reason
      : null;
  return (
    <div
      className={styles.marginNote}
      data-note-key={claimIndex}
      data-tier={tier ?? undefined}
      style={top != null ? { position: "absolute", top: `${top}px` } : undefined}
    >
      <p className={styles.noteKind}>
        {disposition.label}
        {disposition.tier === "assistive" ? (
          <span className={styles.noteTag}>Assistive</span>
        ) : null}
      </p>
      {disposition.detail ? <p className={styles.noteDetail}>{disposition.detail}</p> : null}
      {trail ? <p className={styles.noteTrail}>{trail}</p> : null}
      <button type="button" className={styles.noteAct} onClick={() => onExamine(claimIndex)}>
        Examine
      </button>
    </div>
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
    <section className={styles.tray} aria-label="Statements not located in the draft text">
      <h2 className={styles.trayLabel}>Statements not located in the draft text</h2>
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
