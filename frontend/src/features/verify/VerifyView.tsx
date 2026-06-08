import { useEffect, useRef, useState } from "preact/hooks";

import { Button, ProvenanceBadge, Spinner, Stack, Text, toast } from "@/design-system";
import { ProviderQualityGateBanner } from "@/features/shared";
import {
  briefs as briefsApi,
  verify as verifyApi,
  type VerifyClaimVerdict,
  type VerifyQuoteResult,
  type VerifyResponse
} from "@/services/api/endpoints";

import { buildCertification, fingerprintDraft, type CertificationModel } from "./certification";
import { CertificationExhibit } from "./CertificationExhibit";
import {
  DISPOSITION_ORDER,
  dispositionForClaim,
  type ClaimDisposition
} from "./claimDisposition";
import { ExaminationDrawer } from "./ExaminationDrawer";
import {
  checkedProgress,
  initialStreamState,
  isCardChecking,
  reduceStreamEvent,
  type VerifyStreamState
} from "./streamProgress";
import { WorkspaceMargin } from "./WorkspaceMargin";
import styles from "./VerifyView.module.css";

const SAMPLE_DRAFT =
  "The Supreme Court held in 576 U.S. 644 that same-sex couples have a fundamental right to marry. " +
  "This ruling extended the equal-protection clause to marriage recognition across all states.";

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

interface VerdictSummaryHeadline {
  text: string;
  /** True only when a deterministic flag (citation_not_found / claim_unsupported)
   * is present, so the headline wears the oxblood alarm. could_not_check (an honest
   * refusal) and proposition_unsupported / assessed (assistive judgments) are NOT
   * alarms: a draft of only those reads the neutral "could not be verified" line.
   * Folding could_not_check into the alarm made a single unanchored-but-correct
   * sentence read as a five-alarm "needs review", which is the bug this fixes. */
  problem: boolean;
}

export function verdictSummaryHeadline(dispositions: ClaimDisposition[]): VerdictSummaryHeadline {
  const total = dispositions.length;
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const flagged = count("citation_not_found") + count("claim_unsupported");
  const notVerified =
    count("proposition_unsupported") + count("could_not_check") + count("assessed");
  if (flagged > 0) {
    return { text: `${flagged} of ${total} statements need your review.`, problem: true };
  }
  if (notVerified > 0) {
    return {
      text: `${notVerified} of ${total} statements could not be verified against your sources.`,
      problem: false
    };
  }
  return {
    text: `All ${total} statements are supported by the sources you provided.`,
    problem: false
  };
}

function VerifyVerdictSummary({ dispositions }: VerifySummaryProps) {
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const headline = verdictSummaryHeadline(dispositions);

  // Counts only, problems first. No pass-rate, no percentage: a verdict is a
  // finding, not a score.
  const stats: Array<{ label: string; value: number }> = [
    { label: "Citations not found", value: count("citation_not_found") },
    { label: "Source does not support", value: count("proposition_unsupported") },
    { label: "Unsupported", value: count("claim_unsupported") },
    { label: "Could not verify", value: count("could_not_check") },
    { label: "Supported", value: count("supported") }
  ].filter((s) => s.value > 0);

  return (
    <div className={styles.summary} role="status" aria-live="polite">
      <p
        className={[
          styles.summaryHeadline,
          headline.problem ? styles.summaryHeadlineProblem : ""
        ].join(" ")}
      >
        {headline.text}
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

export function VerifyView({
  briefId,
  initialDraft,
  onDraftChange,
  headerTitle,
  headerSubtitle,
  samplePlaceholder,
}: {
  briefId?: string | null;
  // Host-agnostic props for the standalone Cachet shell. All optional and
  // defaulting to the study app's current behavior, so VerifyView inside Carrel
  // is unchanged when they are absent.
  initialDraft?: string | null;
  onDraftChange?: (value: string) => void;
  headerTitle?: string;
  headerSubtitle?: string;
  samplePlaceholder?: string;
} = {}) {
  const [draft, setDraft] = useState(initialDraft ?? "");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  // claim_index of the statement whose source panel is open, or null.
  const [selected, setSelected] = useState<number | null>(null);
  // ISO timestamp captured when the certification exhibit is opened, or null
  // when closed. Captured once on open so the exhibit timestamp is stable.
  const [certAt, setCertAt] = useState<string | null>(null);
  // Live streaming model (PR3): the per-cite labor as it arrives. The settled
  // verdict render is always driven by `response` (the canonical payload from
  // the `result` event), identical to the non-stream path; `stream` only powers
  // the in-flight working indicator and the per-card "Checking…" state.
  const [stream, setStream] = useState<VerifyStreamState>(initialStreamState);
  const abortRef = useRef<AbortController | null>(null);
  // Cachet PR6b re-hydration seeds (set only when a saved brief is reopened):
  // sealedSeed = the stored seal fingerprint when seal_state === "sealed", so the
  // certification exhibit shows sealed (or cracked, if the draft later differs)
  // without a click; certAtSeed = the stored cert timestamp so a re-export keeps
  // the brief's original date instead of stamping now.
  const [sealedSeed, setSealedSeed] = useState<string | null>(null);
  const [certAtSeed, setCertAtSeed] = useState<string | null>(null);
  // True once this brief is sealed (sealed this session via onSeal, or reopened
  // already-sealed via sealedSeed). The quiet unsealed "Save to Shelf" is hidden
  // when sealed, so a same-draft save can never silently downgrade the seal (the
  // backend upsert is last-write-wins; sealing is the only path to Sealed).
  const [sessionSealed, setSessionSealed] = useState(false);
  // Distinct from `loading` (the live-verify flag): opening a saved brief is a
  // disk fetch, not a verification. Using a separate flag keeps `streaming =
  // loading && !response` false throughout the reopen, so the verify chrome
  // ("Verifying…", "extracting claims") never shows on the no-verify open path.
  const [hydrating, setHydrating] = useState(false);

  // Open a saved brief: re-hydrate the settled view from the STORED response with
  // NO re-verify. Setting `response` renders the whole PR5b surface. The fetch
  // uses `hydrating` (not `loading`) so the live-verify chrome stays dormant.
  // Keyed on briefId; VerifyView is itself keyed on briefId in App.tsx so a
  // brief switch remounts and the seal seed is re-read.
  useEffect(() => {
    if (!briefId) return;
    let live = true;
    const ctrl = new AbortController();
    setHydrating(true);
    setError(null);
    briefsApi
      .get(briefId, { signal: ctrl.signal })
      .then((detail) => {
        if (!live) return;
        // BriefDetail.response/.cert are loose dicts on the wire (the /api/briefs
        // route stores them verbatim, no response_model tightening). Cast once
        // here, the single hydration seam; the render subtree sits under the
        // per-route ErrorBoundary if a stored blob ever drifts from the shape.
        setResponse(detail.response as unknown as VerifyResponse);
        setDraft(detail.draft);
        const storedCert = (detail.cert ?? null) as CertificationModel | null;
        setCertAtSeed(storedCert?.generatedAtISO ?? null);
        setSealedSeed(detail.seal_state === "sealed" ? detail.fingerprint : null);
        // The reopened brief's sealed-ness rides in sealedSeed; clear the
        // session flag so a freshly-reopened unsealed brief can be saved.
        setSessionSealed(false);
      })
      .catch((e) => {
        if (live) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (live) setHydrating(false);
      });
    return () => {
      live = false;
      ctrl.abort();
    };
  }, [briefId]);

  const submit = async () => {
    const trimmed = draft.trim();
    if (!trimmed || loading) return;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setLoading(true);
    setError(null);
    setSelected(null);
    setCertAt(null);
    setResponse(null);
    // A manual re-verify is a NEW check: drop any reopened brief's stored seal
    // and date so the fresh result can never export the prior brief's seal or
    // timestamp (the seeds survive only an untouched re-export of that brief).
    setSealedSeed(null);
    setCertAtSeed(null);
    setSessionSealed(false);
    let live = initialStreamState();
    setStream(live);
    try {
      for await (const event of verifyApi.draftStream(
        { draft: trimmed },
        { signal: controller.signal }
      )) {
        live = reduceStreamEvent(live, event);
        setStream(live);
        if (event.type === "result") {
          setResponse(event.verify);
        } else if (event.type === "error") {
          // Surfaced engine/transport error: show it, never a partial pass.
          setError(event.error);
        }
      }
      // Stream ended without a result event (dropped/truncated). The settled
      // view stays empty rather than reading any un-checked claim as a pass.
      if (live.phase !== "done" && !controller.signal.aborted && !live.error) {
        setError(
          "Verification did not finish. No verdict was produced; nothing was marked supported. Verify the draft again."
        );
      }
    } catch (e) {
      if (!controller.signal.aborted) {
        setError(e instanceof Error ? e.message : String(e));
        setResponse(null);
      }
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      setLoading(false);
    }
  };

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
  const streaming = loading && !response;
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
    <div className={[styles.root, styles.verifyScope].join(" ")}>
      <header className={styles.header}>
        <h1 className={styles.title}>{headerTitle ?? "Verify your draft."}</h1>
        <Text className={styles.subtitle}>
          {headerSubtitle ??
            "Paste a brief, memo, or claim. Every statement is checked against the sources you provide, and any cited cases are checked for existence and holding."}
        </Text>
      </header>

      <div className={styles.draftField}>
        <label className={styles.draftLabel} htmlFor="verify-draft-input">
          Draft
        </label>
        <textarea
          id="verify-draft-input"
          className={styles.draftInput}
          value={draft}
          placeholder={samplePlaceholder ?? SAMPLE_DRAFT}
          onInput={(e) => {
            const value = (e.target as HTMLTextAreaElement).value;
            setDraft(value);
            onDraftChange?.(value);
          }}
          disabled={loading || hydrating}
        />
      </div>

      <div className={styles.actionsRow}>
        <Button onClick={submit} disabled={loading || hydrating || !draft.trim()} type="button">
          {loading ? (
            <Stack direction="horizontal" align="center" gap={2}>
              <Spinner size={16} />
              <span>Verifying…</span>
            </Stack>
          ) : (
            "Verify the draft"
          )}
        </Button>
      </div>

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

          {items.length > 0 && response ? (
            <WorkspaceMargin
              draftText={response.draft_text ?? draft}
              cards={cards}
              unattributedQuotes={quoteResults.filter((q) => q.status !== "verbatim")}
              examined={selected}
              onExamine={(idx) => setSelected(selected === idx ? null : idx)}
            />
          ) : response ? (
            <div className={styles.emptyState}>
              No statements came back from the engine. Load the sources this draft relies on, then
              verify again.
            </div>
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
