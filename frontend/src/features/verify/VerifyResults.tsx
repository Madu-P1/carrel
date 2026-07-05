import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { ProvenanceBadge, toast } from "@/design-system";
import { ProviderQualityGateBanner } from "@/features/shared";
import {
  briefs as briefsApi,
  type VerifyClaimVerdict,
  type VerifyQuoteResult,
  type VerifyQuoteSegment,
  type VerifyStructuralFinding
} from "@/services/api/endpoints";

import { buildCertification, fingerprintDraft } from "./certification";
import { CertificationExhibit } from "./CertificationExhibit";
import {
  DISPOSITION_ORDER,
  dispositionForClaim,
  type ClaimDisposition
} from "./claimDisposition";
import { ExaminationDrawer } from "./ExaminationDrawer";
import { checkedProgress, isCardChecking } from "./streamProgress";
import type { VerifyEngine } from "./useVerify";
import { WorkspaceMargin } from "./WorkspaceMargin";
import styles from "./VerifyView.module.css";

export function tierBadgeClass(tier: ClaimDisposition["tier"]): string {
  switch (tier) {
    case "pass":
      return styles.badgePass;
    case "flag":
      return styles.badgeFlag;
    case "assistive":
      return styles.badgeAssistive;
    case "refusal":
      return styles.badgeRefusal;
    default:
      // Any value outside the known DispositionTier enum — a version-skewed
      // wire shape, a future tier this build doesn't know, or null/undefined
      // slipping past the type system — must fail safe to the honest-refusal
      // class. It must never fall through to badgePass: an unrecognized
      // value was never actually verified.
      return styles.badgeRefusal;
  }
}

/** The holding-match sub-line states derived in CaseVerdictLine. */
export type HoldingKind = "supports" | "ambiguous" | "contradicts" | "unavailable";

// Color class for a holding-match sub-line. A contradiction is an AI judgment,
// so it wears the assistive register (holdingAssistive), never the oxblood
// caseMissing a fabricated citation wears. Exported so the holding-to-class
// seam is unit-locked in dispositionClasses.test.ts, not left to the eye.
export function holdingClass(kind: HoldingKind | null): string {
  switch (kind) {
    case "supports":
      return styles.caseExists;
    case "contradicts":
      return styles.holdingAssistive;
    case "ambiguous":
      return styles.caseAmbiguous;
    case "unavailable":
      return styles.caseError;
    default:
      return "";
  }
}

interface LiveFindingCardProps {
  card: VerifyClaimVerdict;
  disposition: ClaimDisposition;
  /** True while this claim's case check is still in flight (streaming). The
   *  card holds the "Checking" register with skeleton shimmer instead of its
   *  disposition, so a not-yet-checked claim never flashes as a pass. */
  checking: boolean;
}

/** One live findings-rail card (handoff §4): a skeleton that inks in its
 *  verdict when the claim's checks land. Read-only — the examination reads the
 *  settled citation that only exists once the result settles. */
function LiveFindingCard({ card, disposition, checking }: LiveFindingCardProps) {
  if (checking) {
    return (
      <div className={styles.findingCard} data-pending="true" data-tier="checking">
        <span className={styles.findingLabel}>Checking</span>
        <span className={styles.skeletonBar} style={{ width: "70%" }} />
        <span className={styles.skeletonBar} style={{ width: "45%" }} />
      </div>
    );
  }
  return (
    <div className={styles.findingCard} data-tier={disposition.tier}>
      <span className={styles.findingLabel}>{disposition.label}</span>
      {card.claim_text ? <span className={styles.findingTitle}>{card.claim_text}</span> : null}
      {disposition.detail ? (
        <span className={styles.findingDetail}>{disposition.detail}</span>
      ) : null}
    </div>
  );
}

interface VerifySummaryProps {
  dispositions: ClaimDisposition[];
  /** The settled action row (Open exhibit / Save to shelf / New draft),
   *  rendered inside the verdict bar (handoff §4). */
  actions?: preact.ComponentChildren;
  /** Deterministic-path coverage counts (statements/treated/untreated), or
   *  null on the LLM path. Drives the honest scope copy: the legacy "each
   *  statement is checked" line overclaimed for anchor-free prose, which is
   *  examined but not independently checked. */
  coverage?: { statements?: number; treated?: number; untreated?: number } | null;
}

/** The summary's register, as a pure function so tests can pin it: a FLAG is an
 * accusation the lawyer must act on (a cited case that does not exist, or a
 * claim the source contradicts). Could-not-check (an honest refusal),
 * source-does-not-support, and the assistive assessed tier are NOT flags and
 * must never turn the headline into the oxblood alarm; folding them into
 * "needs review" was the "everything needs review" alert fatigue (main #154). */
export function verdictSummaryRegister(dispositions: ClaimDisposition[]): {
  flagged: number;
  notVerified: number;
  headline: string;
} {
  const total = dispositions.length;
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const flagged = count("citation_not_found") + count("claim_unsupported");
  const notVerified = count("proposition_unsupported") + count("could_not_check") + count("assessed");
  const headline =
    flagged > 0
      ? `${flagged} of ${total} statements need your review.`
      : notVerified > 0
        ? `${notVerified} of ${total} statements could not be verified against your sources.`
        : `All ${total} statements are supported by the sources you provided.`;
  return { flagged, notVerified, headline };
}

function VerifyVerdictSummary({ dispositions, coverage, actions }: VerifySummaryProps) {
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const citationNotFound = count("citation_not_found");
  const propositionUnsupported = count("proposition_unsupported");
  const claimUnsupported = count("claim_unsupported");
  const couldNotCheck = count("could_not_check");
  const supported = count("supported");
  const { flagged, headline } = verdictSummaryRegister(dispositions);

  // Counts only, problems first. No pass-rate, no percentage: a verdict is a
  // finding, not a score.
  const stats: Array<{ label: string; value: number }> = [
    { label: "Citations not found", value: citationNotFound },
    { label: "Source does not support", value: propositionUnsupported },
    { label: "Unsupported", value: claimUnsupported },
    { label: "Could not verify", value: couldNotCheck },
    // T1 (ADR-0012): zero until the selector ships, but listed so the stat
    // row always sums to the total once assessed cards go live.
    { label: "Assessed (local model)", value: count("assessed") },
    { label: "Supported", value: supported }
  ].filter((s) => s.value > 0);

  return (
    <div className={styles.summary} role="status" aria-live="polite">
      <div className={styles.verdictBar}>
        <p
          className={[
            styles.summaryHead,
            styles.summaryHeadline,
            flagged > 0 ? styles.summaryHeadlineProblem : ""
          ].join(" ")}
        >
          {headline}
        </p>
        <span className={styles.summaryCounts}>
          {stats.map((s) => (
            <span key={s.label} className={styles.summaryStat}>
              {s.label} <span className={styles.summaryCount}>{s.value}</span>
            </span>
          ))}
        </span>
        {actions ? <div className={styles.summaryActions}>{actions}</div> : null}
      </div>
      {coverage && (coverage.untreated ?? 0) > 0 ? (
        <p className={styles.scopeNote}>
          {(coverage.untreated ?? 0) === 1
            ? "1 of "
            : `${coverage.untreated} of `}
          {coverage.statements ?? 0} statements carried no checkable anchor (such as a citation,
          quotation, amount, or date) and {(coverage.untreated ?? 0) === 1 ? "was" : "were"} not independently
          checked; {(coverage.untreated ?? 0) === 1 ? "it renders" : "they render"} as plain text
          below.
        </p>
      ) : null}
      <p className={styles.scopeNote}>
        Each statement carrying a checkable anchor is checked against the sources you provide. This
        confirms grounding, not legal correctness or strategy.
      </p>
    </div>
  );
}

/**
 * The zero-finding state, made honest. A deterministic verify that produced no
 * cards (a clean prose draft where every sentence is anchor-free) used to render
 * as silent draft read-back: no summary, no scope line, nothing. To the user
 * that reads as "the tool did nothing." The engine still reports HOW MUCH it
 * examined via the `coverage` block, so we surface a quiet, non-alarm statement
 * of exactly that: it read N statements, found no checkable anchor, and so left
 * them unverified rather than passing them. This is the "anchor-free prose gets
 * a COVERAGE statement" decision; it wears the neutral ink register (role=status,
 * no problem headline), never the oxblood alarm that the removed per-claim
 * "needs review" noise wore.
 */
function EmptyCoveragePanel({ statements }: { statements: number }) {
  const noun = statements === 1 ? "statement" : "statements";
  return (
    <div className={styles.summary} role="status" aria-live="polite" data-empty-coverage="true">
      <p className={styles.summaryHeadline}>No checkable claims in this draft.</p>
      <p className={styles.scopeNote}>
        Cachet read {statements} {noun}. None carried a checkable anchor (a citation, a quotation, an
        amount, or a date), so there was nothing to verify against your sources. Cachet confirms
        grounding, not prose: a statement with no checkable anchor is left unverified, never passed.
      </p>
    </div>
  );
}

/**
 * The zero-finding state for paths that carry no `coverage` block (the LLM
 * path, or a deterministic run with coverage.statements === 0). Without this,
 * a settled, error-free result with zero claim cards rendered nothing at all
 * here — a blank container a lawyer could misread as a silent all-clear.
 * Generic by design: it makes no claim about how many statements were read,
 * since that count is exactly what's missing on this path.
 */
function EmptyClaimsPanel() {
  return (
    <div className={styles.summary} role="status" aria-live="polite" data-empty-claims="true">
      <p className={styles.summaryHeadline}>No checkable claims found in this document.</p>
    </div>
  );
}

function quoteStatusLabel(status: VerifyQuoteResult["status"]): string {
  switch (status) {
    case "altered":
      return "Not found verbatim";
    case "could_not_check":
      return "Could not check";
    default:
      return "Verbatim";
  }
}

interface QuotePanelProps {
  quotes: VerifyQuoteResult[];
}

/**
 * The quote autopsy. An altered quote is rendered with its genuine words in ink
 * and its fabricated words struck through in the single oxblood accent, so the
 * lawyer sees exactly which words the engine could not find verbatim in any
 * cited source — the moment an existence-only citation checker passes but Cachet
 * does not. The segments ARE the per-phrase verdict the deterministic engine
 * already reached (services.legal.quote_check); they concatenate back to the
 * exact quote, so this surface adds no claim of its own and ships no source
 * text. A quote with no segments (a could-not-check refusal, or an older
 * payload) renders plainly: the strike is reserved for a real, confident flag.
 */
function QuoteBody({ quote, segments }: { quote: string; segments?: VerifyQuoteSegment[] }) {
  if (!segments || segments.length === 0) return <>“{quote}”</>;
  return (
    <>
      “
      {segments.map((seg, i) => (
        <span
          key={`${i}-${seg.kind}`}
          data-kind={seg.kind}
          className={
            seg.kind === "altered"
              ? styles.quoteFabricated
              : seg.kind === "verbatim"
                ? styles.quoteGenuine
                : undefined
          }
        >
          {seg.text}
        </span>
      ))}
      ”
    </>
  );
}

/**
 * Cachet PR4: brief-level draft-quote-verbatim panel. Lists the quoted passages
 * that need attention (altered or could-not-check); a fully-verbatim quote is
 * the unmarked pass and is not listed. Brief-level: not yet attributed to a
 * specific claim (PR5 claim-span alignment does that). Deterministic flags wear
 * the oxblood register via styles.quoteAltered; could-not-check is the quiet
 * refusal. No confidence numbers, by design.
 */
function QuotePanel({ quotes }: QuotePanelProps) {
  const flagged = quotes.filter((q) => q.status !== "verbatim");
  if (flagged.length === 0) return null;
  return (
    <section className={styles.quotePanel} aria-label="Quotation check">
      <h2 className={styles.quotePanelTitle}>Quotation check</h2>
      <ul className={styles.quoteList}>
        {flagged.map((q) => (
          <li
            key={q.index}
            className={[
              styles.quoteItem,
              q.status === "altered" ? styles.quoteAltered : styles.quoteUnplaceable
            ].join(" ")}
          >
            <span className={styles.quoteStatus}>{quoteStatusLabel(q.status)}</span>
            <blockquote className={styles.quoteText}>
              <QuoteBody quote={q.quote} segments={q.segments} />
            </blockquote>
          </li>
        ))}
      </ul>
      <p className={styles.scopeNote}>
        This checks that the words shown in quotation marks appear in the sources checked, as written.
        It does not assess whether an omission changes the meaning.
      </p>
    </section>
  );
}

/** The mono-uppercase status label for a structural finding. A flagged
 * defined-term-unused is a confident catch; the could-not-check kinds are review
 * prompts (the reference or value could not be confirmed). */
export function structuralStatusLabel(finding: VerifyStructuralFinding): string {
  switch (finding.kind) {
    case "defined_term_unused":
      return "Defined term unused";
    case "dangling_cross_reference":
      return "Reference unverified";
    case "internal_contradiction":
      return "Possible inconsistency";
    default:
      return finding.disposition === "flagged" ? "Flagged" : "Could not check";
  }
}

interface StructuralPanelProps {
  findings: VerifyStructuralFinding[];
}

/**
 * Cachet SI-5: document-level structural-integrity panel. Lists the engine's
 * intra-document findings — a flagged defined-term-unused catch wears the oxblood
 * register, the could-not-check review prompts (unresolved cross-references,
 * possible inconsistencies) wear the quiet hairline. Draft-level, a sibling to the
 * quotation check. Returns null when the engine surfaced nothing. No green, no
 * confidence numbers, by design.
 */
function StructuralPanel({ findings }: StructuralPanelProps) {
  if (findings.length === 0) return null;
  return (
    <section className={styles.structurePanel} aria-label="Structure check">
      <h2 className={styles.structurePanelTitle}>Structure check</h2>
      <ul className={styles.structureList}>
        {findings.map((finding, i) => (
          <li
            key={`${finding.kind}-${finding.target ?? ""}-${finding.start}-${i}`}
            className={[
              styles.structureItem,
              finding.disposition === "flagged" ? styles.structureFlag : styles.structureReview
            ].join(" ")}
          >
            <span className={styles.structureStatus}>{structuralStatusLabel(finding)}</span>
            <p className={styles.structureDetail}>{finding.detail}</p>
          </li>
        ))}
      </ul>
      <p className={styles.scopeNote}>
        This checks the document against itself: that cross-references resolve and defined terms are
        used. A flag is a confident defect; a review item could not be confirmed and may point to
        another document.
      </p>
    </section>
  );
}

/**
 * A null/undefined/non-object entry in claim_verdicts or a streamed claims
 * batch (a malformed payload, a dropped SSE frame) must not crash the verdict
 * render: dispositionForClaim and the card body both read properties straight
 * off `card`, which throws on null/undefined rather than failing safe.
 */
function isUsableCard(card: unknown): card is VerifyClaimVerdict {
  return typeof card === "object" && card !== null;
}

/**
 * The verdict surface: everything downstream of "the engine has something to
 * show". It renders the streaming progress, the live skeleton, and the settled
 * verdict tree (summary, quote panel, per-claim cards, the document margin, the
 * examination drawer, and the certification exhibit), and owns the interaction
 * state tightly coupled to that render — which claim is examined, whether the
 * certification exhibit is open, and the human's session seal. The data it
 * renders comes from a `VerifyEngine`; the same component serves Carrel's
 * VerifyView and the Cachet lectern unchanged.
 *
 * Scope contract: this renders only the `.results` column and reads the
 * verifyScope design tokens (paper surfaces, the oxblood flag) from an ancestor.
 * Host it inside a `verifyScope` container — VerifyView and the lectern both do.
 */
export function VerifyResults({
  engine,
  draft,
  onResolve,
  onNewDraft
}: {
  engine: VerifyEngine;
  /** The composer's current draft text. Used as the fallback document text for
   *  the margin and the save fingerprint when the response omits draft_text. */
  draft: string;
  /** The shell's resolve-the-refusal action: when a statement could not be
   *  checked for want of the record it relies on, this routes the user to where
   *  they load it (Sources, on the Cachet lectern). When omitted (Carrel, which
   *  has no Sources surface) the refusal CTA is not rendered at all. */
  onResolve?: () => void;
  /** Returns the host to a fresh composer (handoff §4 "New draft"). The
   *  composer yields the page to the run view, so the way back lives here.
   *  Omitted on hosts (Carrel, the brief reader) that keep their own frame. */
  onNewDraft?: () => void;
}) {
  const { response, stream, loading, hydrating, error, sealedSeed, certAtSeed } = engine;
  // claim_index of the statement whose source panel is open, or null.
  const [selected, setSelected] = useState<number | null>(null);
  // ISO timestamp captured when the certification exhibit is opened, or null
  // when closed. Captured once on open so the exhibit timestamp is stable.
  const [certAt, setCertAt] = useState<string | null>(null);
  // True once this brief is sealed this session via onSeal. The quiet unsealed
  // "Save to Shelf" is hidden when sealed so a same-draft save can never silently
  // downgrade the seal (the backend upsert is last-write-wins; sealing is the
  // only path to Sealed).
  const [sessionSealed, setSessionSealed] = useState(false);

  // A new result (a fresh verify, or a reopened brief) resets the interaction
  // state: close any open source panel and certification exhibit, and drop the
  // prior session seal. A reopened brief's sealed-ness rides in `sealedSeed`
  // (engine state), so isSealed below still reflects it.
  useEffect(() => {
    setSelected(null);
    setCertAt(null);
    setSessionSealed(false);
  }, [response]);

  // SM-V7 command spine: the seal and export verbs from the ⌘K palette open
  // the certification exhibit (this component owns it). Sealing stays the
  // human's click inside the exhibit; a command must never set the seal
  // itself. Only the Cachet palette dispatches this event, so Carrel hosts
  // carry an inert listener. The ref keeps registration to one listener while
  // reading the current response/seed.
  const openCertRef = useRef(() => {});
  openCertRef.current = () => {
    if (!response) {
      toast.error("No verdict to certify yet. Verify the draft first.");
      return;
    }
    setCertAt(certAtSeed ?? new Date().toISOString());
  };
  useEffect(() => {
    function onCommand(event: Event) {
      const id = (event as CustomEvent<{ id?: string }>).detail?.id;
      if (id === "seal" || id === "export") openCertRef.current();
    }
    window.addEventListener("cachet:command", onCommand);
    return () => window.removeEventListener("cachet:command", onCommand);
  }, []);

  // The text the verdict actually covers vs the text on the composer right
  // now. The verdict persists across navigation (and the composer stays
  // editable after a check), so without this comparison an edited draft would
  // sit directly above a confident "All N statements are supported" the
  // engine never saw — the product's stated worst failure. Plain trimmed
  // string equality: verify() trims before sending and the engine echoes the
  // cleaned text back as draft_text. An EMPTIED composer is left undecided
  // (no banner) so the brief-hydration window, where the response lands a
  // frame before the composer seeds, cannot flash a false stale notice.
  const checkedText = response?.draft_text ?? null;
  const draftStale =
    checkedText !== null && draft.trim() !== "" && draft.trim() !== checkedText.trim();

  // Memoized so WorkspaceMargin's own [draftText, cards] memo actually hits:
  // a fresh .filter() array per render silently defeated it, re-running full
  // segmentation + displaySafe over the whole document on every examine click
  // (the measurable hot path on long drafts).
  const cards = useMemo(
    () => (response?.claim_verdicts ?? []).filter(isUsableCard),
    [response]
  );
  // O5: malformed cards (null / non-object) are filtered out so the render
  // stays crash-safe (the finding cards and dispositionForClaim read properties
  // straight off the card). But a dropped claim must not vanish SILENTLY —
  // count the drop so an honest note can state it below. A real deterministic
  // run ~never emits these; this is a robustness backstop for a malformed or
  // partial payload, and stating "N could not be read" is more honest than a
  // claim count that quietly shrinks.
  const droppedClaimCount = (response?.claim_verdicts?.length ?? 0) - cards.length;
  // Compute one disposition per claim, then order flags first, the honest
  // refusal next, and the unmarked passes last. The not-confirmed set is the
  // headline of the surface.
  const items = useMemo(
    () =>
      cards
        .map((card) => ({ card, disposition: dispositionForClaim(card) }))
        .sort(
          (a, b) => DISPOSITION_ORDER[a.disposition.kind] - DISPOSITION_ORDER[b.disposition.kind]
        ),
    [cards]
  );
  const selectedItem =
    selected != null ? (items.find((it) => it.card.claim_index === selected) ?? null) : null;
  // T71: a run is only "settled" once it has a response AND carries no error
  // at either level: the stream/engine `error`, or a payload-level
  // `response.error` — e.g. a degraded-provider result other than the
  // specially-handled "provider_below_quality_bar" literal (the outer
  // ternary below routes that one case to its own banner). `!!response`
  // alone was the only gate on the items-based summary, the save/export
  // actions, and the WorkspaceMargin's inline marks, so any OTHER
  // response.error value fell through unfiltered and could still render a
  // "Supported" badge on top of a failure. `verify()` only ever assigns
  // `response` the fully-settled `result` payload (never a partial one), so
  // `!!response` on its own already carries the "run has genuinely finished"
  // guarantee for the non-error case — `loading` is deliberately NOT part of
  // this gate, since it can lag `response` by one microtask of bookkeeping
  // cleanup and gating on it produced a transient blackout of already-final
  // content. Every affirmative panel below reads `settled` so an errored
  // response can never flash a badge on top of it.
  const settled = !!response && !error && !response.error;
  // The zero-finding state: a settled deterministic verdict that produced no
  // cards (every statement was anchor-free). The engine still reports how many
  // statements it read in `coverage`, so surface an honest coverage statement
  // instead of rendering the draft back in silence.
  const examinedStatements = response?.coverage?.statements ?? 0;
  const showEmptyCoverage = settled && items.length === 0 && examinedStatements > 0;
  // The generic zero-claims fallback: any settled, error-free result with no
  // claim cards and no usable coverage count (the LLM path carries no
  // coverage block at all; a deterministic run can also report 0 statements
  // read). Without this branch the result rendered as a blank container.
  const showEmptyClaims = settled && items.length === 0 && !showEmptyCoverage;
  // Memoized: buildCertification runs a full synchronous SHA-256 over the
  // draft. Keyed on the checked text (draft_text when the engine echoes it,
  // which the deterministic path always does), so re-renders from typing or
  // stream bookkeeping do not redo the digest while the exhibit is open.
  const certDraftText = response?.draft_text ?? draft;
  const certModel = useMemo(
    () => (certAt && response ? buildCertification(response, certAt, certDraftText) : null),
    [certAt, response, certDraftText]
  );
  // The sheet's CURRENT text, fingerprinted so a seal set on since-edited text
  // reads cracked on the live flow. Memoized (one SHA-256 per draft change
  // while the exhibit is open, none while it is closed) instead of inline in
  // JSX, where every stream/selection re-render redid the digest.
  const currentFingerprint = useMemo(
    () =>
      certAt !== null
        ? fingerprintDraft(draft.trim() !== "" ? draft.trim() : (response?.draft_text ?? ""))
        : null,
    [certAt, draft, response]
  );

  // A sealed brief is already on the Shelf as Sealed; the quiet unsealed Save is
  // hidden so it can never downgrade the seal (sealing is the only path to Sealed).
  const isSealed = sessionSealed || sealedSeed !== null;

  // Statements the user can resolve by providing the record. Scoped to
  // could-not-check refusals whose card came back `unknown` (verification could
  // not run for want of a source), NOT the verified-downgrade refusals (an
  // ambiguous citation, a lookup error) that loading a record would not fix.
  // Pointing those at Sources would be a dishonest CTA, the one thing the refusal
  // surface must never be.
  const resolvableRefusals = items.filter(
    (it) => it.disposition.kind === "could_not_check" && it.card.verdict === "unknown"
  ).length;

  // Cachet PR6d: persist this checked brief to the Shelf. "sealed" comes from
  // the human sealing the certification (seal == save); "unsealed" from the
  // quiet Save-to-Shelf action. The backend upserts by fingerprint, so saving
  // then sealing the same draft updates one row rather than duplicating it.
  async function saveToShelf(sealState: "sealed" | "unsealed") {
    if (!response) return;
    const draftText = response.draft_text ?? draft;
    try {
      await briefsApi.save({
        draft: draftText,
        fingerprint: fingerprintDraft(draftText),
        response: response as unknown as Record<string, unknown>,
        cert: certModel as unknown as Record<string, unknown> | null,
        seal_state: sealState
      });
      toast.success(sealState === "sealed" ? "Sealed and saved to the Shelf" : "Saved to the Shelf");
    } catch (e) {
      toast.error("Could not save to the Shelf", e instanceof Error ? e.message : undefined);
    }
  }

  // Live skeleton (PR3): while the stream is in flight and before the canonical
  // result has settled, render the skeleton cards from the `claims` event with
  // each not-yet-checked claim in its "Checking…" register. These are computed
  // through the SAME pure `dispositionForClaim`, but a checking card overrides
  // the badge so a claim never flashes a pass before its cite check lands.
  // A stream error drops the live list at once: the skeleton cards carry the
  // grounding verdict with no case verdicts, so holding them on screen after
  // the failure would read half-checked claims as findings. The error banner
  // is the only verdict an errored stream gets (refuse over accuse).
  const streaming = loading && !response && stream.phase !== "error";
  const liveItems =
    streaming && stream.cards.length > 0
      ? stream.cards
          .filter(isUsableCard)
          .map((card) => ({ card, disposition: dispositionForClaim(card) }))
          .sort(
            (a, b) => DISPOSITION_ORDER[a.disposition.kind] - DISPOSITION_ORDER[b.disposition.kind]
          )
      : [];
  const progress = checkedProgress(stream);
  // Cachet PR4: brief-level draft-quote-verbatim results. Settled view reads the
  // canonical payload; live view shows the quote_batch the moment it lands. Only
  // surface quotes that need attention (altered / could-not-check); a fully
  // verbatim quote needs no callout (absence of a flag is the pass).
  const quoteResults = response?.quote_results ?? stream.quotes ?? [];
  // The live read-back's paragraph split, computed once per draft instead of
  // per SSE frame (every cite_verdict re-renders this component; the draft
  // cannot change mid-stream).
  const streamParagraphs = useMemo(
    () => (streaming ? draft.split(/\n{2,}/).filter((para) => para.trim()) : []),
    [streaming, draft]
  );
  const structuralFindings = response?.structural_findings ?? [];

  return (
    <div
      className={styles.results}
      data-verify-results
      // Drives the wide-viewport shift that keeps the record readable beside
      // the fixed Examination drawer instead of underneath it.
      data-exam-open={selectedItem != null ? "true" : undefined}
    >
      {/* role=alert: a verification failure or refusal ("nothing was marked
          supported") is the one state a reviewer must never miss, so it is
          announced assertively. It fires once (error is set once per failed
          check), so there is no per-cite re-announce risk the streaming
          indicator below is aria-hidden to avoid. */}
      {error ? (
        <div className={styles.errorBanner} role="alert">
          <span className={styles.errorLabel}>The check did not finish</span>
          <p className={styles.errorBody}>{error}</p>
          {draft.trim() && !loading ? (
            <button
              type="button"
              className={styles.errorRetry}
              onClick={() => void engine.verify(draft)}
            >
              Run the check again
            </button>
          ) : null}
        </div>
      ) : null}

      {hydrating && !response ? (
        // Opening a saved brief is a disk fetch, not a verification. Honest
        // neutral copy so the no-verify promise holds for the whole fetch window
        // (including a slow or offline backend), never "Verifying…".
        <div className={styles.progressLine} aria-hidden="true">
          <span className={styles.progressDot} />
          <span className={styles.progressLabel}>Opening saved brief…</span>
        </div>
      ) : null}

      {streaming ? (
        // Visual-only progress affordance: no aria-live. A polite live region
        // here would re-announce on every cite_verdict (the holding-match checks
        // land seconds apart), spamming a screen reader with "2 of 7", "3 of 7".
        // The settled verdict summary carries its own role=status announcement.
        <div className={styles.progressLine} aria-hidden="true">
          <span className={styles.progressDot} />
          <span className={styles.progressLabel}>
            {stream.phase === "checking" && progress.total > 0
              ? `Checking citations · ${progress.checked} of ${progress.total}`
              : "Reading the draft and extracting claims…"}
          </span>
        </div>
      ) : null}

      {loading ? (
        // One announcement that the check is running: CONSTANT text for the
        // whole stream so the live region fires exactly once, never per cite.
        // Visually hidden (inline, not a CSS class: the entry CSS budget sits
        // bytes from its ceiling); the settled summary announces the outcome.
        <span
          role="status"
          style={{
            position: "absolute",
            width: "1px",
            height: "1px",
            overflow: "hidden",
            clipPath: "inset(50%)"
          }}
        >
          Verifying the draft against your sources.
        </span>
      ) : null}

      {streaming && liveItems.length > 0 ? (
        <div className={styles.settledGrid}>
          <article className={styles.readback} aria-hidden="true">
            <div className={styles.colEyebrow}>Draft · read-back</div>
            {streamParagraphs.map((para, pi) => (
              <p key={pi} className={styles.docParagraph}>
                {para}
              </p>
            ))}
          </article>
          <aside className={styles.findingsRail} aria-label="Findings, checking">
            <div className={styles.colEyebrow}>Findings · worst first</div>
            {liveItems.map((it, i) => (
              <LiveFindingCard
                key={`live-${it.card.claim_index}-${i}`}
                card={it.card}
                disposition={it.disposition}
                checking={isCardChecking(stream, it.card)}
              />
            ))}
          </aside>
        </div>
      ) : null}

      {response?.error === "provider_below_quality_bar" ? (
        <ProviderQualityGateBanner provider={response.provider ?? ""} surface="verification" />
      ) : response?.error ? (
        // O7: any OTHER payload-level error (weak_coverage, empty_retrieval, an
        // arbitrary provider string) must surface an honest failure, not
        // silently blank the results column. The `settled` gate correctly
        // suppresses every affirmative panel for such a payload, but nothing
        // else rendered in its place — so a reviewer saw a bare provenance badge
        // and no verdict. This states the failure plainly. (Effectively dead on
        // Cachet's deterministic path, which always sets error=null; a real gap
        // in this shared component off that path.)
        <div className={styles.errorBanner} role="alert" data-response-error={response.error}>
          Verification could not be completed, so nothing here is confirmed.
        </div>
      ) : (
        <>
          {draftStale ? (
            // The stale register leads the settled verdict: every pixel below
            // it describes the EARLIER text. Quiet note, not oxblood — the
            // verdict is not wrong, it is outdated — with the one honest next
            // move wired to the current draft.
            <div className={styles.resolveRefusal} role="note" data-stale-draft="true">
              <p className={styles.resolveRefusalText}>
                The draft has changed since this check. The verdict below covers the earlier
                text, not your latest edits.
              </p>
              <button
                type="button"
                className={styles.resolveRefusalAction}
                onClick={() => void engine.verify(draft)}
                disabled={loading}
              >
                Verify the draft again
              </button>
            </div>
          ) : null}

          {response && response.provider ? (
            <div className={styles.provenanceRow}>
              <ProvenanceBadge provider={response.provider} />
            </div>
          ) : null}

          {settled && items.length > 0 ? (
            <VerifyVerdictSummary
              dispositions={items.map((it) => it.disposition)}
              coverage={response?.coverage ?? null}
              actions={
                <>
                  <button
                    type="button"
                    className={styles.actionPrimary}
                    onClick={() => setCertAt(certAtSeed ?? new Date().toISOString())}
                  >
                    Open exhibit
                  </button>
                  {!isSealed ? (
                    <button
                      type="button"
                      className={styles.actionOutline}
                      onClick={() => void saveToShelf("unsealed")}
                    >
                      Save to Shelf
                    </button>
                  ) : null}
                  {onNewDraft ? (
                    <button type="button" className={styles.actionQuiet} onClick={onNewDraft}>
                      New draft
                    </button>
                  ) : null}
                </>
              }
            />
          ) : showEmptyCoverage ? (
            <EmptyCoveragePanel statements={examinedStatements} />
          ) : showEmptyClaims ? (
            <EmptyClaimsPanel />
          ) : null}

          {droppedClaimCount > 0 ? (
            // O5: malformed claims were dropped from the render for crash-safety.
            // State it plainly so the claim count never shrinks in silence.
            <div className={styles.resolveRefusal} role="note" data-dropped-claims={droppedClaimCount}>
              <p className={styles.resolveRefusalText}>
                {droppedClaimCount === 1
                  ? "1 claim could not be read from the result and is not shown."
                  : `${droppedClaimCount} claims could not be read from the result and are not shown.`}
              </p>
            </div>
          ) : null}

          {onResolve && resolvableRefusals > 0 ? (
            // The refusal made actionable: when Cachet could not check a
            // statement for want of the record it relies on, give the one honest
            // next move. Quiet, not a flag: the refusal is correct, not an error.
            <div className={styles.resolveRefusal} role="note">
              <p className={styles.resolveRefusalText}>
                {resolvableRefusals === 1
                  ? "1 statement could not be checked without the record it relies on."
                  : `${resolvableRefusals} statements could not be checked without the records they rely on.`}
              </p>
              <button type="button" className={styles.resolveRefusalAction} onClick={onResolve}>
                Open the Vault to load it
              </button>
            </div>
          ) : null}

          <QuotePanel quotes={quoteResults} />

          {settled && <StructuralPanel findings={structuralFindings} />}

          {settled ? (
            // Render the draft as the document either way. With claim cards it shows
            // their inline marks and margin notes; with none (a clean prose draft where
            // every sentence is untreated) it shows the draft as plain text, no marks and
            // no "could not verify" message. Untreated prose is not a finding, so it just
            // reads back as the draft (mirrors main #155). Gated on `settled` (not just
            // `response`): the inline marks are the same "Supported" claim as the summary
            // badge, so a non-terminal or errored response must not render them either.
            <WorkspaceMargin
              draftText={response?.draft_text ?? draft}
              cards={cards}
              examined={selected}
              onExamine={(idx) => setSelected(selected === idx ? null : idx)}
            />
          ) : null}
        </>
      )}

      {settled && items.length > 0 ? (
        <ExaminationDrawer
          card={selectedItem?.card ?? null}
          open={selectedItem != null}
          onClose={() => setSelected(null)}
        />
      ) : null}

      {certModel ? (
        <CertificationExhibit
          model={certModel}
          sealedFingerprint={sealedSeed}
          // The sheet's CURRENT text, so a seal set on text that has since
          // been edited reads cracked on the live flow too, not only on a
          // reopened brief. Computed only while the exhibit is open (one
          // SHA-256 per open, not per keystroke).
          currentFingerprint={currentFingerprint ?? undefined}
          onSeal={() => {
            setSessionSealed(true);
            // Record the live seal on the ENGINE too: sessionSealed is render
            // state and dies with this component, so on a persistent-store
            // host (the lectern) a remount would re-show the quiet Save,
            // whose upsert silently downgrades the seal. The engine seed is
            // what survives — and it is what a reopened exhibit reads. The
            // PAIR is recorded (fingerprint + timestamp) so a reopened
            // exhibit re-renders the original seal date, never a fresh one.
            engine.markSealed(certModel.fingerprint, certModel.generatedAtISO);
            void saveToShelf("sealed");
          }}
          onClose={() => setCertAt(null)}
        />
      ) : null}
    </div>
  );
}
