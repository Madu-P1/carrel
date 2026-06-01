import { useRef, useState } from "preact/hooks";

import { Button, ProvenanceBadge, Spinner, Stack, Text } from "@/design-system";
import { ProviderQualityGateBanner } from "@/features/shared";
import {
  verify as verifyApi,
  type VerifyClaimVerdict,
  type VerifyResponse
} from "@/services/api/endpoints";

import { buildCertification } from "./certification";
import { CertificationExhibit } from "./CertificationExhibit";
import {
  DISPOSITION_ORDER,
  dispositionForClaim,
  type ClaimDisposition
} from "./claimDisposition";
import { SourceInspector } from "./SourceInspector";
import {
  checkedProgress,
  initialStreamState,
  isCardChecking,
  reduceStreamEvent,
  type VerifyStreamState
} from "./streamProgress";
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

function VerifyVerdictSummary({ dispositions }: VerifySummaryProps) {
  const total = dispositions.length;
  const count = (kind: ClaimDisposition["kind"]) =>
    dispositions.filter((d) => d.kind === kind).length;
  const citationNotFound = count("citation_not_found");
  const propositionUnsupported = count("proposition_unsupported");
  const claimUnsupported = count("claim_unsupported");
  const couldNotCheck = count("could_not_check");
  const supported = count("supported");
  const needsReview = citationNotFound + propositionUnsupported + claimUnsupported + couldNotCheck;

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
        className={[styles.summaryHeadline, needsReview > 0 ? styles.summaryHeadlineProblem : ""].join(
          " "
        )}
      >
        {needsReview > 0
          ? `${needsReview} of ${total} statements need your review.`
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

export function VerifyView() {
  const [draft, setDraft] = useState("");
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

  return (
    <div className={[styles.root, styles.verifyScope].join(" ")}>
      <header className={styles.header}>
        <h1 className={styles.title}>Verify your draft.</h1>
        <Text className={styles.subtitle}>
          Paste a brief, memo, or claim. Every statement is checked against the sources you provide,
          and any cited cases are checked for existence and holding.
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
          placeholder={SAMPLE_DRAFT}
          onInput={(e) => setDraft((e.target as HTMLTextAreaElement).value)}
          disabled={loading}
        />
      </div>

      <div className={styles.actionsRow}>
        <Button onClick={submit} disabled={loading || !draft.trim()} type="button">
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

          {items.length > 0 ? (
            <div className={styles.resultActions}>
              <button
                type="button"
                className={styles.exportCert}
                onClick={() => setCertAt(new Date().toISOString())}
              >
                Export certification
              </button>
            </div>
          ) : null}

          {items.length > 0 ? (
            <div className={[styles.workspace, selectedItem ? styles.workspaceSplit : ""].join(" ")}>
              <div className={styles.verdictList}>
                {items.map((it, i) => (
                  <VerdictCard
                    key={`${it.card.claim_index}-${i}`}
                    card={it.card}
                    disposition={it.disposition}
                    index={i}
                    isSelected={selectedItem?.card.claim_index === it.card.claim_index}
                    onInspect={() =>
                      setSelected(
                        selected === it.card.claim_index ? null : (it.card.claim_index ?? null)
                      )
                    }
                  />
                ))}
              </div>
              {selectedItem ? (
                <SourceInspector
                  card={selectedItem.card}
                  disposition={selectedItem.disposition}
                  onClose={() => setSelected(null)}
                />
              ) : null}
            </div>
          ) : response ? (
            <div className={styles.emptyState}>
              No statements came back from the engine. Load the sources this draft relies on, then
              verify again.
            </div>
          ) : null}
        </>
      )}

      {certModel ? (
        <CertificationExhibit model={certModel} onClose={() => setCertAt(null)} />
      ) : null}
    </div>
  );
}
