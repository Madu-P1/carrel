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
import { useEffect, useMemo, useRef, useState } from "preact/hooks";

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

  // The findings carousel position. One finding shows at a time, centered; its
  // error is highlighted in the document above, and both advance together.
  const railKey = railClaims.join(",");
  const [activeIndex, setActiveIndex] = useState(0);
  // A fresh verify (a new set of findings) returns the carousel to the first.
  useEffect(() => {
    setActiveIndex(0);
  }, [railKey]);
  const clampedActive = railClaims.length > 0 ? Math.min(activeIndex, railClaims.length - 1) : 0;
  const activeClaimIndex = railClaims.length > 0 ? railClaims[clampedActive] : null;

  // Bring the active finding's mark into view in the document as the carousel
  // advances, so the highlighted error is always visible beside its card.
  const bodyRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (activeClaimIndex == null) return;
    const mark = bodyRef.current?.querySelector<HTMLElement>(
      `[data-claim-index="${activeClaimIndex}"]`
    );
    // scrollIntoView is absent in the test DOM (jsdom/happy-dom); guard so the
    // effect never throws where the API is unimplemented.
    if (!mark || typeof mark.scrollIntoView !== "function") return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    mark.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [activeClaimIndex]);

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
                  isActive={activeClaimIndex === seg.claimIndex}
                  onExamine={onExamine}
                />
              )
            )}
          </p>
        ))}
      </div>

      {/* The findings are reviewed one at a time: a single card centered in
          view, its error highlighted in the document above. Advancing (an arrow
          button, the Left/Right arrow keys, a horizontal scroll, or a swipe)
          slides the card and moves the highlight to the next finding. */}
      {railClaims.length > 0 ? (
        <FindingsCarousel
          claims={railClaims}
          metaByIndex={metaByIndex}
          activeIndex={clampedActive}
          setActiveIndex={setActiveIndex}
          onExamine={onExamine}
        />
      ) : null}

      {hasTray ? (
        <UnplacedTray
          claims={trayClaims}
          onExamine={onExamine}
        />
      ) : null}
    </div>
  );
}

/**
 * The findings carousel: one finding card centered at a time. Advancing slides
 * the track (a CSS transition on transform, not a keyframe, so the verifyScope
 * motion guard holds and reduced-motion makes it instant) and the parent moves
 * the document highlight to match. Four ways to advance: the arrow buttons, the
 * Left/Right arrow keys, a horizontal wheel/trackpad scroll, and a pointer
 * swipe. Dots give direct access and show position.
 */
function FindingsCarousel({
  claims,
  metaByIndex,
  activeIndex,
  setActiveIndex,
  onExamine
}: {
  claims: number[];
  metaByIndex: Map<number, ClaimMeta>;
  activeIndex: number;
  setActiveIndex: (next: number) => void;
  onExamine: (claimIndex: number) => void;
}) {
  const total = claims.length;
  const go = (next: number) => setActiveIndex(Math.max(0, Math.min(total - 1, next)));
  const prev = () => go(activeIndex - 1);
  const next = () => go(activeIndex + 1);

  // One horizontal wheel gesture moves one card; the lock keeps a flick from
  // skating across every finding at once.
  const wheelLock = useRef(false);
  function onWheel(e: WheelEvent) {
    if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) || Math.abs(e.deltaX) < 16) return;
    e.preventDefault();
    if (wheelLock.current) return;
    wheelLock.current = true;
    if (e.deltaX > 0) next();
    else prev();
    window.setTimeout(() => {
      wheelLock.current = false;
    }, 340);
  }

  // Pointer swipe past a threshold advances in the dragged direction.
  const startX = useRef<number | null>(null);
  function onPointerDown(e: PointerEvent) {
    startX.current = e.clientX;
  }
  function onPointerUp(e: PointerEvent) {
    if (startX.current == null) return;
    const dx = e.clientX - startX.current;
    startX.current = null;
    if (Math.abs(dx) < 44) return;
    if (dx < 0) next();
    else prev();
  }

  function onKeyDown(e: KeyboardEvent) {
    if (e.key === "ArrowRight") {
      e.preventDefault();
      next();
    } else if (e.key === "ArrowLeft") {
      e.preventDefault();
      prev();
    } else if (e.key === "Home") {
      e.preventDefault();
      go(0);
    } else if (e.key === "End") {
      e.preventDefault();
      go(total - 1);
    }
  }

  const activeLabel = metaByIndex.get(claims[activeIndex])?.disposition.label ?? "";

  return (
    <div
      className={styles.carousel}
      role="group"
      aria-roledescription="carousel"
      aria-label={`Findings, ${total} total`}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onWheel={onWheel}
      onPointerDown={onPointerDown}
      onPointerUp={onPointerUp}
    >
      <div className={styles.carouselStage}>
        <button
          type="button"
          className={styles.carouselArrow}
          aria-label="Previous finding"
          disabled={activeIndex === 0}
          onClick={prev}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6" /></svg>
        </button>

        <div className={styles.carouselViewport}>
          <div
            className={styles.carouselTrack}
            style={{ transform: `translateX(-${activeIndex * 100}%)` }}
          >
            {claims.map((idx) => {
              const meta = metaByIndex.get(idx);
              if (!meta) return null;
              return (
                <MarginNote
                  key={idx}
                  claimIndex={idx}
                  disposition={meta.disposition}
                  card={meta.card}
                  onExamine={onExamine}
                />
              );
            })}
          </div>
        </div>

        <button
          type="button"
          className={styles.carouselArrow}
          aria-label="Next finding"
          disabled={activeIndex === total - 1}
          onClick={next}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6" /></svg>
        </button>
      </div>

      {total > 1 ? (
        <div className={styles.carouselDots}>
          {claims.map((idx, i) => (
            <button
              key={idx}
              type="button"
              className={[styles.carouselDot, i === activeIndex ? styles.carouselDotActive : ""]
                .filter(Boolean)
                .join(" ")}
              aria-label={`Finding ${i + 1} of ${total}`}
              aria-current={i === activeIndex ? "true" : undefined}
              onClick={() => go(i)}
            />
          ))}
        </div>
      ) : null}

      {/* aria-live (without role=status) announces the active finding to a
          screen reader without adding a second status landmark that the verdict
          summary already owns. */}
      <p className={styles.carouselStatus} aria-live="polite">
        Finding {activeIndex + 1} of {total}: {activeLabel}
      </p>
    </div>
  );
}

function ClaimMark({
  segment,
  meta,
  isExamined,
  isActive,
  onExamine
}: {
  segment: ClaimSegment;
  meta: ClaimMeta | undefined;
  isExamined: boolean;
  /** True when this is the finding currently centered in the carousel; the mark
   *  wears a soft highlight so the eye links the card to its error. */
  isActive: boolean;
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
        isExamined ? styles.claimMarkExamined : "",
        isActive ? styles.claimMarkActive : ""
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
    </span>
  );
}

function MarginNote({
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
