import { navigateTo } from "@/app/shell/useAppShell";
import { buildReaderChunkPath } from "@/features/reader/hooks/useChunkDeepLink";

import styles from "./SourceCitation.module.css";

export interface SourceCitationProps {
  /** Source document id. Required: the citation row only renders when the
   *  caller has a deep-link target. */
  documentId: string;
  /** Human-readable filename. Falls back to "this document" if empty. */
  documentName: string | null | undefined;
  /** Chunk id from the bound anchor. Required for the deep-link to land on
   *  the exact passage; without it, the parent should not render this
   *  component (the back face hides the citation row). */
  chunkId: string;
  /** 1-indexed page number. Hidden when null (non-paginated source). */
  pageNum?: number | null;
  /** Verbatim quote from the anchor. Rendered as the excerpt; truncated
   *  to ~40 words so a 500-word chunk doesn't crowd the answer body. */
  quoteText?: string | null;
}

const EXCERPT_WORD_LIMIT = 40;

function truncateToWords(text: string, limit: number): string {
  const trimmed = text.trim();
  if (!trimmed) return "";
  const parts = trimmed.split(/\s+/);
  if (parts.length <= limit) return trimmed;
  return `${parts.slice(0, limit).join(" ")}…`;
}

/**
 * Source citation rendered on the back face of an SRS flashcard.
 *
 * Carrel's wedge is verbatim source-grounding: every AI-drafted card was
 * promoted from an anchor pointing at a specific chunk on a specific
 * page. The SRS loop is the surface where students see that grounding
 * most often. Click-through deep-links to the reader scrolled and
 * highlighted at the originating chunk.
 *
 * The whole row is a button so the touch/click target is generous and
 * keyboard-accessible. Activation routes through `navigateTo` so the
 * action matches how the rest of the app traverses routes (no full
 * page reload under file:// in the bundled WKWebView).
 */
export function SourceCitation({
  documentId,
  documentName,
  chunkId,
  pageNum,
  quoteText,
}: SourceCitationProps) {
  const docLabel = (documentName ?? "").trim() || "this document";
  const headerText = pageNum != null && pageNum > 0
    ? `From ${docLabel}, page ${pageNum}`
    : `From ${docLabel}`;
  const excerpt = truncateToWords(quoteText ?? "", EXCERPT_WORD_LIMIT);

  const handleActivate = (): void => {
    navigateTo(buildReaderChunkPath(documentId, chunkId));
  };

  return (
    <button
      type="button"
      className={styles.citation}
      onClick={handleActivate}
      aria-label={`Open the source for this card: ${headerText}`}
    >
      <span className={styles.header}>{headerText}</span>
      {excerpt ? <span className={styles.excerpt}>{`“${excerpt}”`}</span> : null}
      <span className={styles.openHint} aria-hidden="true">Open in reader →</span>
    </button>
  );
}
