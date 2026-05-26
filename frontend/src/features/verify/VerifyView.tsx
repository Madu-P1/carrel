import { useState } from "preact/hooks";

import { Button, Spinner, Stack, Text } from "@/design-system";
import { CitationChip } from "@/features/ask/components/CitationChip";
import type { CitationRecord } from "@/features/ask/types";
import {
  verify as verifyApi,
  type VerifyClaimVerdict,
  type VerifyResponse
} from "@/services/api/endpoints";

import styles from "./VerifyView.module.css";

const SAMPLE_DRAFT =
  "The Supreme Court held in 576 U.S. 644 that same-sex couples have a fundamental right to marry. " +
  "This ruling extended the equal-protection clause to marriage recognition across all states.";

function verdictBadgeClass(verdict: VerifyClaimVerdict["verdict"]): string {
  switch (verdict) {
    case "verified":
      return styles.verdictBadgeVerified;
    case "unsupported":
      return styles.verdictBadgeUnsupported;
    default:
      return styles.verdictBadgeUnknown;
  }
}

function verdictLabel(verdict: VerifyClaimVerdict["verdict"]): string {
  switch (verdict) {
    case "verified":
      return "Verified";
    case "unsupported":
      return "Unsupported";
    default:
      return "Unknown";
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
  };
}

function CaseVerdictLine({ verdict }: CaseLineProps) {
  // Map CourtListener per-citation status to a verdict color. 200 is a
  // confirmed single match (green), 300 is ambiguous (amber), 404 is
  // not found (red), 400 is malformed reporter (red).
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
  return (
    <div className={[styles.caseVerdictLine, colorClass].join(" ")}>
      <span className={styles.caseDot} aria-hidden />
      <span>{verdict.citation}</span>
      <span style={{ opacity: 0.7 }}>— {label}</span>
      {verdict.case_name ? <span>· {verdict.case_name}</span> : null}
      {verdict.absolute_url ? (
        <a
          href={verdict.absolute_url}
          target="_blank"
          rel="noopener noreferrer"
          className={styles.caseLink}
        >
          source
        </a>
      ) : null}
    </div>
  );
}

interface VerdictCardProps {
  card: VerifyClaimVerdict;
  index: number;
}

function VerdictCard({ card, index }: VerdictCardProps) {
  const citations = (card.citations ?? []) as unknown as CitationRecord[];
  const caseBatches = card.case_verdicts ?? [];
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
    <article className={styles.verdictCard}>
      <header className={styles.verdictHeader}>
        <span className={styles.verdictIndex}>[{index + 1}]</span>
        <span className={[styles.verdictBadge, verdictBadgeClass(card.verdict)].join(" ")}>
          {verdictLabel(card.verdict)}
        </span>
      </header>
      <p className={styles.claimText}>{card.claim_text}</p>
      {card.unsupported_reason ? (
        <p className={styles.unsupportedReason}>{card.unsupported_reason}</p>
      ) : null}
      {citations.length > 0 ? (
        <div className={styles.chipsRow}>
          {citations.map((citation, i) => (
            <CitationChip
              key={`${citation.document_id}-${String(citation.node_id)}-${i}`}
              citation={citation}
              index={i + 1}
            />
          ))}
        </div>
      ) : null}
      {caseLines.length > 0 ? (
        <div className={styles.caseVerdictsRow}>
          {caseLines.map((line, i) =>
            line.batchError ? (
              <div key={`err-${i}`} className={[styles.caseVerdictLine, styles.caseError].join(" ")}>
                Case verification unavailable
                {line.batchErrorCode ? ` (${line.batchErrorCode})` : ""}
                {line.batchErrorMessage ? ` — ${line.batchErrorMessage}` : ""}
              </div>
            ) : (
              <CaseVerdictLine key={`case-${i}`} verdict={line.verdict!} />
            )
          )}
        </div>
      ) : null}
    </article>
  );
}

interface VerifySummaryProps {
  summary: NonNullable<VerifyResponse["summary"]>;
}

function VerifySummaryRow({ summary }: VerifySummaryProps) {
  return (
    <div className={styles.summaryRow} role="status" aria-live="polite">
      <span className={styles.summaryStat}>
        Total <span className={styles.summaryCount}>{summary.total}</span>
      </span>
      <span className={styles.summaryStat}>
        Verified <span className={styles.summaryCount}>{summary.verified}</span>
      </span>
      <span className={styles.summaryStat}>
        Unsupported <span className={styles.summaryCount}>{summary.unsupported}</span>
      </span>
      <span className={styles.summaryStat}>
        Unknown <span className={styles.summaryCount}>{summary.unknown}</span>
      </span>
    </div>
  );
}

export function VerifyView() {
  const [draft, setDraft] = useState("");
  const [loading, setLoading] = useState(false);
  const [response, setResponse] = useState<VerifyResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const trimmed = draft.trim();
    if (!trimmed || loading) return;
    setLoading(true);
    setError(null);
    try {
      const result = await verifyApi.draft({ draft: trimmed });
      setResponse(result);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setResponse(null);
    } finally {
      setLoading(false);
    }
  };

  const cards = (response?.claim_verdicts ?? []) as VerifyClaimVerdict[];
  const summary = response?.summary ?? null;

  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <h1 className={styles.title}>Verify your draft.</h1>
        <Text className={styles.subtitle}>
          Paste a brief, memo, or claim. Carrel grounds every statement against your sources and
          checks any cited cases against CourtListener.
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
            "Verify"
          )}
        </Button>
      </div>

      {error ? <div className={styles.errorBanner}>{error}</div> : null}

      {summary ? <VerifySummaryRow summary={summary} /> : null}

      {cards.length > 0 ? (
        <div className={styles.verdictList}>
          {cards.map((card, i) => (
            <VerdictCard key={`${card.claim_index}-${i}`} card={card} index={i} />
          ))}
        </div>
      ) : response ? (
        <div className={styles.emptyState}>
          No claims came back from the engine. Try a different draft.
        </div>
      ) : null}
    </div>
  );
}
