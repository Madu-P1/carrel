import type { DocumentDetail } from "@/services/api/endpoints";

import styles from "./SourcePanel.module.css";

type ReaderDocument = DocumentDetail["document"];

/**
 * MetadataStripe — compact doc header in the right rail.
 *
 * Replaces the old bordered MetadataCard. The old version was a rounded
 * card that ate ~140px of vertical space duplicating what the toolbar
 * already shows (file type, filename). The stripe is a 2-line block at
 * the top of the rail with a hairline divider below, not a card:
 *
 *   LINE 1  [PDF chip] filename                  [confidence pill]
 *   LINE 2  Biology · 4 pages · updated Apr 20
 *
 * The stripe gives back real estate for what the rail is actually for:
 * chunks, concepts, notes, and related.
 */
export function MetadataStripe({
  doc,
  summary
}: {
  doc: ReaderDocument;
  summary: string;
}) {
  const ft = (doc.file_type || "DOC").toUpperCase();
  const confidenceValue =
    typeof doc.confidence === "number" ? Math.round(doc.confidence * 100) : null;
  const confidenceLabel =
    confidenceValue != null ? `Confidence ${confidenceValue}%` : "Confidence n/a";
  const confidenceTone: "good" | "warn" | "low" | "unknown" =
    confidenceValue == null
      ? "unknown"
      : confidenceValue >= 85
        ? "good"
        : confidenceValue >= 65
          ? "warn"
          : "low";

  const metaBits: string[] = [];
  if (doc.subject_name) metaBits.push(doc.subject_name);
  if (typeof doc.page_count === "number") {
    metaBits.push(`${doc.page_count} ${doc.page_count === 1 ? "page" : "pages"}`);
  }
  if (doc.updated_at) {
    metaBits.push(`updated ${formatDate(doc.updated_at)}`);
  } else if (doc.upload_date) {
    metaBits.push(`uploaded ${formatDate(doc.upload_date)}`);
  }

  return (
    <header aria-label="Document metadata" className={styles.stripe}>
      <div className={styles.stripeTopRow}>
        {/* Chip is purely visual; screen readers already announce the
         *  filename next to it, so we don't double up with aria-label.
         *  The PdfToolbar's file-type chip owns the labeled role. */}
        <span className={styles.stripeChip} aria-hidden>
          {ft}
        </span>
        <h2 className={styles.stripeTitle} title={doc.filename}>
          {doc.filename}
        </h2>
        <span
          className={[styles.stripeConfidence, styles[`confidence-${confidenceTone}`]].join(" ")}
        >
          {confidenceLabel}
        </span>
      </div>
      {metaBits.length > 0 ? (
        <p className={styles.stripeMeta}>{metaBits.join(" · ")}</p>
      ) : null}
      {summary ? <p className={styles.stripeSummary}>{summary}</p> : null}
    </header>
  );
}

/**
 * Best-effort date formatter. The API returns ISO strings; we want the
 * stripe to read "Apr 20" not a 25-char timestamp. Falls back to the raw
 * value if parsing fails so the UI never silently drops the info.
 */
function formatDate(raw: string): string {
  try {
    const d = new Date(raw);
    if (Number.isNaN(d.valueOf())) return raw;
    return d.toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return raw;
  }
}
