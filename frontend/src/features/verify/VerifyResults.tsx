import { useEffect, useState } from "preact/hooks";

import { ProvenanceBadge, Spinner, toast } from "@/design-system";
import { ProviderQualityGateBanner } from "@/features/shared";
import {
  briefs as briefsApi,
  type VerifyClaimVerdict,
  type VerifyQuoteResult
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
    case "flag":
      return styles.badgeFlag;
    case "assistive":
      return styles.badgeAssistive;
    case "refusal":
      return styles.badgeRefusal;
    default:
      return styles.badgePass;
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

interface CaseLineProps {
  verdict: {
    citation: string;
    status: number;
    exists: boolean;
    case_name?: string | null;
    absolute_url?: string | null;
    court?: string | null;
    date_filed?: string | null;
    error_message?: string | null;
    // Carrel V2 half-2 holding-match fields. Populated when the
    // cite exists (status=200) and the opinion fetch + Claude
    // verifier succeeded.
    holding_match?: boolean | null;
    holding_concern?: string | null;
    holding_excerpt?: string | null;
    holding_error?: string | null;
  };
}

function CaseVerdictLine({ verdict }: CaseLineProps) {
  // Map CourtListener per-citation status to a verdict color. 200 is a
  // confirmed single match, 300 is ambiguous, 404 is not found, 400 is
  // malformed reporter. PR3 replaces these traffic-light hues with the
  // scoped paper-and-oxblood palette; the claim-level disposition badge
  // already carries the headline verdict.
  const colorClass = verdict.exists
    ? styles.caseExists
    : verdict.status === 300
      ? styles.caseAmbiguous
      : styles.caseMissing;
  const label = verdict.exists
    ? "Case found"
    : verdict.status === 300
      ? "Ambiguous (multiple matches)"
      : verdict.status === 404
        ? "Case not found"
        : verdict.status === 400
          ? "Malformed citation"
          : "Verification error";
  // Carrel V2 half-2: derive a holding-match sub-line state.
  type HoldingState = {
    kind: HoldingKind;
    label: string;
    detail?: string;
    excerpt?: string;
  };
  let holding: HoldingState | null = null;
  if (verdict.exists) {
    if (verdict.holding_error) {
      holding = {
        kind: "unavailable",
        label: "Holding check unavailable",
        detail: verdict.holding_error
      };
    } else if (verdict.holding_match === true) {
      holding = {
        kind: "supports",
        label: "Opinion supports the claim",
        detail: verdict.holding_concern ?? undefined,
        excerpt: verdict.holding_excerpt ?? undefined
      };
    } else if (verdict.holding_match === false) {
      holding = {
        kind: "contradicts",
        label: "Opinion does NOT support the claim",
        detail: verdict.holding_concern ?? undefined,
        excerpt: verdict.holding_excerpt ?? undefined
      };
    } else if (
      verdict.holding_match === null
      && (verdict.holding_concern || verdict.holding_excerpt)
    ) {
      holding = {
        kind: "ambiguous",
        label: "Holding ambiguous",
        detail: verdict.holding_concern ?? undefined
      };
    }
  }
  const holdingColorClass = holdingClass(holding ? holding.kind : null);
  return (
    <div className={styles.caseVerdictGroup}>
      <div className={[styles.caseVerdictLine, colorClass].join(" ")}>
        <span className={styles.caseDot} aria-hidden />
        <span>{verdict.citation}</span>
        <span style={{ opacity: 0.7 }}>· {label}</span>
        {verdict.case_name ? <span>· {verdict.case_name}</span> : null}
      </div>
      {holding ? (
        <div className={[styles.holdingMatchLine, holdingColorClass].join(" ")}>
          <span className={styles.holdingDot} aria-hidden />
          <span className={styles.holdingLabel}>{holding.label}</span>
          {holding.detail ? (
            <span className={styles.holdingDetail}>· {holding.detail}</span>
          ) : null}
          {holding.excerpt ? (
            <div className={styles.holdingExcerpt}>“{holding.excerpt}”</div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

interface VerdictCardProps {
  card: VerifyClaimVerdict;
  disposition: ClaimDisposition;
  index: number;
  isSelected: boolean;
  onInspect: () => void;
  /** True while this claim's case check is still in flight (streaming). The
   *  card shows a quiet "Checking…" register instead of its disposition badge,
   *  so a not-yet-checked claim never flashes as a pass. */
  checking?: boolean;
  /** When false, the card is a read-only preview (the live streaming list):
   *  no "View source" affordance, since the inspector reads the settled
   *  citation that only exists once the result lands. Default true. */
  interactive?: boolean;
}

function VerdictCard({
  card,
  disposition,
  index,
  isSelected,
  onInspect,
  checking = false,
  interactive = true
}: VerdictCardProps) {
  const caseBatches = card.case_verdicts ?? [];
  const citationCount = (card.citations ?? []).length;
  const caseCount = caseBatches.reduce(
    (n, batch) => n + (batch.ok ? (batch.verdicts ?? []).length : 0),
    0
  );
  const sourceCount = citationCount + caseCount;
  // Flatten case verdicts across all batches attached to this claim;
  // V1 emits at most one batch per claim, but the API leaves it open.
  type CaseLine =
    | {
        batchError: true;
        batchErrorCode: string | null;
        batchErrorMessage: string | null;
      }
    | {
        batchError: false;
        verdict: CaseLineProps["verdict"];
      };
  const caseLines: CaseLine[] = caseBatches.flatMap((batch): CaseLine[] => {
    if (!batch.ok) {
      return [
        {
          batchError: true,
          batchErrorCode: batch.error_code ?? null,
          batchErrorMessage: batch.error_message ?? null
        }
      ];
    }
    return (batch.verdicts ?? []).map((v) => ({
      batchError: false,
      verdict: v as CaseLineProps["verdict"]
    }));
  });
  return (
    <article
      className={[
        styles.verdictCard,
        isSelected ? styles.verdictCardSelected : "",
        checking ? styles.verdictCardChecking : ""
      ].join(" ")}
      data-tier={checking ? "checking" : disposition.tier}
    >
      <header className={styles.verdictHeader}>
        <span className={styles.verdictIndex}>[{index + 1}]</span>
        {checking ? (
          <span className={[styles.verdictBadge, styles.badgeChecking].join(" ")}>
            <Spinner size={16} />
            <span>Checking…</span>
          </span>
        ) : (
          <span className={[styles.verdictBadge, tierBadgeClass(disposition.tier)].join(" ")}>
            {disposition.label}
          </span>
        )}
      </header>
      <p className={styles.claimText}>{card.claim_text}</p>
      {!checking && disposition.detail ? (
        <p className={styles.dispositionDetail}>{disposition.detail}</p>
      ) : null}
      {caseLines.length > 0 ? (
        <div className={styles.caseVerdictsRow}>
          {caseLines.map((line, i) =>
            line.batchError ? (
              <div key={`err-${i}`} className={[styles.caseVerdictLine, styles.caseError].join(" ")}>
                Case verification unavailable
                {line.batchErrorCode ? ` (${line.batchErrorCode})` : ""}
                {line.batchErrorMessage ? ` · ${line.batchErrorMessage}` : ""}
              </div>
            ) : (
              <CaseVerdictLine key={`case-${i}`} verdict={line.verdict!} />
            )
          )}
        </div>
      ) : null}
      {interactive ? (
        <div className={styles.cardFoot}>
          <button
            type="button"
            className={styles.viewSource}
            onClick={onInspect}
            aria-pressed={isSelected}
          >
            {isSelected
              ? "Hide source"
              : sourceCount > 0
                ? `View source (${sourceCount})`
                : "View source"}
          </button>
        </div>
      ) : null}
    </article>
  );
}

interface VerifySummaryProps {
  dispositions: ClaimDisposition[];
}

function VerifyVerdictSummary({ dispositions }: VerifySummaryProps) {
  const total = dispositions.length;
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const citationNotFound = count("citation_not_found");
  const propositionUnsupported = count("proposition_unsupported");
  const claimUnsupported = count("claim_unsupported");
  const couldNotCheck = count("could_not_check");
  const supported = count("supported");
  // A flag is an accusation the lawyer must act on: a cited case that does not
  // exist, or a claim the source contradicts. Could-not-check (an honest refusal),
  // source-does-not-support, and the assistive assessed tier are NOT flags, so they
  // must not turn the headline into the oxblood alarm. Folding them into "needs
  // review" was the "everything needs review" alert fatigue (mirrors main #154).
  const flagged = citationNotFound + claimUnsupported;
  const notVerified = propositionUnsupported + couldNotCheck + count("assessed");

  // Counts only, problems first. No pass-rate, no percentage: a verdict is a
  // finding, not a score.
  const stats: Array<{ label: string; value: number }> = [
    { label: "Citations not found", value: citationNotFound },
    { label: "Source does not support", value: propositionUnsupported },
    { label: "Unsupported", value: claimUnsupported },
    { label: "Could not verify", value: couldNotCheck },
    { label: "Supported", value: supported }
  ].filter((s) => s.value > 0);

  return (
    <div className={styles.summary} role="status" aria-live="polite">
      <p
        className={[styles.summaryHeadline, flagged > 0 ? styles.summaryHeadlineProblem : ""].join(
          " "
        )}
      >
        {flagged > 0
          ? `${flagged} of ${total} statements need your review.`
          : notVerified > 0
            ? `${notVerified} of ${total} statements could not be verified against your sources.`
            : `All ${total} statements are supported by the sources you provided.`}
      </p>
      <div className={styles.summaryRow}>
        {stats.map((s) => (
          <span key={s.label} className={styles.summaryStat}>
            {s.label} <span className={styles.summaryCount}>{s.value}</span>
          </span>
        ))}
      </div>
      <p className={styles.scopeNote}>
        Each statement is checked against the sources you provide. This confirms grounding, not
        legal correctness or strategy.
      </p>
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
            <blockquote className={styles.quoteText}>“{q.quote}”</blockquote>
          </li>
        ))}
      </ul>
      <p className={styles.scopeNote}>
        This checks that the words shown in quotation marks appear in the cited source as written.
        It does not assess whether an omission changes the meaning.
      </p>
    </section>
  );
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
  onResolve
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

  const cards = (response?.claim_verdicts ?? []) as VerifyClaimVerdict[];
  // Compute one disposition per claim, then order flags first, the honest
  // refusal next, and the unmarked passes last. The not-confirmed set is the
  // headline of the surface.
  const items = cards
    .map((card) => ({ card, disposition: dispositionForClaim(card) }))
    .sort((a, b) => DISPOSITION_ORDER[a.disposition.kind] - DISPOSITION_ORDER[b.disposition.kind]);
  const selectedItem =
    selected != null ? (items.find((it) => it.card.claim_index === selected) ?? null) : null;
  const certModel = certAt && response ? buildCertification(response, certAt) : null;
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

  return (
    <div className={styles.results} data-verify-results>
      {error ? <div className={styles.errorBanner}>{error}</div> : null}

      {hydrating && !response ? (
        // Opening a saved brief is a disk fetch, not a verification. Honest
        // neutral copy so the no-verify promise holds for the whole fetch window
        // (including a slow or offline backend), never "Verifying…".
        <div className={styles.workingIndicator} aria-hidden="true">
          <Spinner size={16} />
          <span className={styles.workingLabel}>Opening saved brief…</span>
        </div>
      ) : null}

      {streaming ? (
        // Visual-only progress affordance: no aria-live. A polite live region
        // here would re-announce on every cite_verdict (the holding-match checks
        // land seconds apart), spamming a screen reader with "2 of 7", "3 of 7".
        // The settled verdict summary carries its own role=status announcement.
        <div className={styles.workingIndicator} aria-hidden="true">
          <Spinner size={16} />
          <span className={styles.workingLabel}>
            {stream.phase === "checking" && progress.total > 0
              ? `Checking citations · ${progress.checked} of ${progress.total}`
              : "Reading the draft and extracting claims…"}
          </span>
        </div>
      ) : null}

      {streaming && liveItems.length > 0 ? (
        <div className={styles.workspace}>
          <div className={styles.verdictList}>
            {liveItems.map((it, i) => (
              <VerdictCard
                key={`live-${it.card.claim_index}-${i}`}
                card={it.card}
                disposition={it.disposition}
                index={i}
                isSelected={false}
                onInspect={() => {}}
                checking={isCardChecking(stream, it.card)}
                interactive={false}
              />
            ))}
          </div>
        </div>
      ) : null}

      {response?.error === "provider_below_quality_bar" ? (
        <ProviderQualityGateBanner provider={response.provider ?? ""} surface="verification" />
      ) : (
        <>
          {response && response.provider ? (
            <div className={styles.provenanceRow}>
              <ProvenanceBadge provider={response.provider} />
            </div>
          ) : null}

          {items.length > 0 ? (
            <VerifyVerdictSummary dispositions={items.map((it) => it.disposition)} />
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

          {items.length > 0 ? (
            <div className={styles.resultActions}>
              {!isSealed ? (
                <button
                  type="button"
                  className={styles.saveShelf}
                  onClick={() => void saveToShelf("unsealed")}
                >
                  Save to Shelf
                </button>
              ) : null}
              <button
                type="button"
                className={styles.exportCert}
                onClick={() => setCertAt(certAtSeed ?? new Date().toISOString())}
              >
                Export certification
              </button>
            </div>
          ) : null}

          {response ? (
            // Render the draft as the document either way. With claim cards it shows
            // their inline marks and margin notes; with none (a clean prose draft where
            // every sentence is untreated) it shows the draft as plain text, no marks and
            // no "could not verify" message. Untreated prose is not a finding, so it just
            // reads back as the draft (mirrors main #155). A genuine engine error still
            // surfaces above via the error banner.
            <WorkspaceMargin
              draftText={response.draft_text ?? draft}
              cards={cards}
              examined={selected}
              onExamine={(idx) => setSelected(selected === idx ? null : idx)}
            />
          ) : null}
        </>
      )}

      {response && items.length > 0 ? (
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
          onSeal={() => {
            setSessionSealed(true);
            void saveToShelf("sealed");
          }}
          onClose={() => setCertAt(null)}
        />
      ) : null}
    </div>
  );
}
