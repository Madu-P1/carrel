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
import { useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";

import type { VerifyClaimVerdict, VerifyQuoteResult } from "@/services/api/endpoints";

import { DISPOSITION_ORDER, dispositionForClaim, type ClaimDisposition } from "./claimDisposition";
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

/** SM-V7 keyboard path: the index to focus next when cycling findings with
 *  j/k. `current` is -1 when nothing in the set is focused yet (j -> first,
 *  k -> last); otherwise it wraps. Pure so it can be tested without the DOM. */
export function nextFocusIndex(count: number, current: number, dir: 1 | -1): number {
  if (count <= 0) return -1;
  if (current < 0) return dir === 1 ? 0 : count - 1;
  return (current + dir + count) % count;
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
  /** quote results that could not be attributed to a placed claim (tray header). */
  unattributedQuotes: VerifyQuoteResult[];
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
  unattributedQuotes,
  examined,
  onExamine
}: WorkspaceMarginProps) {
  const metaByIndex = new Map<number, ClaimMeta>();
  cards.forEach((card, i) => {
    const idx = typeof card.claim_index === "number" ? card.claim_index : i;
    metaByIndex.set(idx, { card, disposition: dispositionForClaim(card) });
  });

  const segments = segmentDraft(draftText, cards);
  const paragraphs = paragraphsFromSegments(segments);

  // Non-supported PLACED claims get a rail note. (Supported = unmarked, no note.
  // Unplaced = no span here, lives in the tray.)
  const placedClaimIndices = segments
    .filter((s): s is ClaimSegment => s.kind === "claim")
    .map((s) => s.claimIndex);
  const railClaims = placedClaimIndices.filter((idx) => {
    const meta = metaByIndex.get(idx);
    return meta ? noteTier(meta.disposition.tier) !== null : false;
  });

  // Unplaced claims (no span produced) -> the tray, worst-first.
  const placedSet = new Set(placedClaimIndices);
  const trayClaims = cards
    .map((card, i) => (typeof card.claim_index === "number" ? card.claim_index : i))
    .filter((idx) => !placedSet.has(idx))
    .map((idx) => metaByIndex.get(idx)!)
    .filter(Boolean)
    .sort((a, b) => DISPOSITION_ORDER[a.disposition.kind] - DISPOSITION_ORDER[b.disposition.kind]);

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

  // SM-V7 keyboard path: j/k move focus between the flagged findings (the
  // non-pass marks) so a reviewer can walk the document hands-on, a clerk down
  // the page. Each mark is already a button, so Enter or ⌥↵ drills it open via
  // its own handler. Guarded so j/k still type normally in any text field
  // (the draft, the command palette). Reads the DOM fresh, so it stays correct
  // as findings stream in and re-sort; bound once.
  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "j" && event.key !== "k") return;
      const active = document.activeElement as HTMLElement | null;
      if (
        active &&
        (active.tagName === "INPUT" ||
          active.tagName === "TEXTAREA" ||
          active.isContentEditable)
      ) {
        return;
      }
      const body = bodyRef.current;
      if (!body) return;
      const marks = Array.from(
        body.querySelectorAll<HTMLElement>("[data-claim-index]")
      ).filter((el) => el.dataset.tier && el.dataset.tier !== "pass");
      if (marks.length === 0) return;
      event.preventDefault();
      const current = active ? marks.indexOf(active) : -1;
      const next = nextFocusIndex(marks.length, current, event.key === "j" ? 1 : -1);
      marks[next]?.focus();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const topFor = (idx: number): number | undefined =>
    placements.find((p) => p.key === idx)?.top;

  const hasTray = trayClaims.length > 0 || unattributedQuotes.length > 0;

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
          quotes={unattributedQuotes}
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

  // SM-V3 The Catch: the one motion worth breaking the near-zero-motion rule for
  // (operator-approved 2026-06-03 as the 2nd exception after the seal). On a
  // deterministic flag, the oxblood underline draws across the dead claim left
  // to right, like a proofreader's pen: Cachet strikes what it cannot stand
  // behind. The rule is a background gradient (box-decoration-break: clone, so
  // it follows every wrapped line) and we draw it by animating background-size
  // via WAAPI, not a CSS keyframe, so the verifyScope motion guard holds. The
  // resting CSS is the full-width rule, so reduced-motion and re-renders simply
  // show the struck mark.
  const markRef = useRef<HTMLSpanElement | null>(null);
  useEffect(() => {
    if (tier !== "flag") return;
    const el = markRef.current;
    if (!el || typeof el.animate !== "function") return;
    if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) return;
    // No fill: the CSS resting state is the full-width rule, so once this ends
    // the element rests on the visible strike. During [0,360ms] it draws 0->100%.
    const anim = el.animate(
      [{ backgroundSize: "0% 2px" }, { backgroundSize: "100% 2px" }],
      { duration: 360, easing: "cubic-bezier(0.2, 0, 0, 1)" }
    );
    // Safety net: a fabricated-cite strike must never be left invisible if the
    // animation clock stalls (backgrounded/throttled tab). finish() jumps to the
    // end; with no fill the element then rests on the CSS full-width rule.
    const t = window.setTimeout(() => {
      try {
        anim.finish();
      } catch {
        /* already finished or cancelled */
      }
    }, 800);
    return () => window.clearTimeout(t);
  }, [tier]);
  const aria =
    tier === "pass"
      ? `Statement, checked and supported: ${segment.text}`
      : `Statement flagged ${label}${fuzzy ? ", placement approximate" : ""}: ${segment.text}`;
  return (
    <span
      ref={markRef}
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
  const trail = card.unsupported_reason && tier === "refusal" ? card.unsupported_reason : null;
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
      {disposition.nextAction ? (
        // SM-V5: the calibrating "do this". A refusal that hands responsibility
        // back with a precise next step, never a shrug. Rendered as a directive
        // line, not a dead button, since source ingest is not wired yet.
        <p className={styles.noteAction}>{disposition.nextAction}</p>
      ) : null}
      <button type="button" className={styles.noteAct} onClick={() => onExamine(claimIndex)}>
        Examine
      </button>
    </div>
  );
}

function UnplacedTray({
  claims,
  quotes,
  onExamine
}: {
  claims: ClaimMeta[];
  quotes: VerifyQuoteResult[];
  onExamine: (claimIndex: number) => void;
}) {
  return (
    <section className={styles.tray} aria-label="Statements not located in the draft text">
      <h2 className={styles.trayLabel}>Statements not located in the draft text</h2>
      <p className={styles.trayNote}>
        These statements were checked, but their exact wording could not be matched to a span in the
        draft above. Review them here.
      </p>
      {quotes.length > 0 ? (
        <div className={styles.trayQuotes}>
          <h3 className={styles.trayQuotesLabel}>Quotation checks</h3>
          {quotes.map((q) => (
            <p
              key={q.index}
              className={[
                styles.trayQuoteItem,
                q.status === "altered" ? styles.trayQuoteAltered : styles.trayQuoteUnplaceable
              ].join(" ")}
            >
              <span className={styles.trayQuoteStatus}>
                {q.status === "altered" ? "Not found verbatim" : "Could not check"}
              </span>
              <span className={styles.trayQuoteText}>“{q.quote}”</span>
            </p>
          ))}
        </div>
      ) : null}
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
