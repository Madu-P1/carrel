import { useCallback, useEffect, useState } from "preact/hooks";

import { Badge, Button, Card, Icon, Spinner, Stack, Text } from "@/design-system";
import {
  library,
  type DuplicateGroup,
  type DuplicatePreview
} from "@/services/api/endpoints";

import styles from "./DuplicateCleanupPanel.module.css";

interface DuplicateCleanupPanelProps {
  onCleanupComplete: () => void;
}

/**
 * Library dedupe control surface.
 *
 * Flow:
 *   1. Mount → GET /api/library/duplicates. If zero, render nothing (no
 *      noise when the library is clean).
 *   2. If duplicates exist, show a compact banner: "N duplicate sources
 *      found · Review." The banner itself is low-weight — it's diagnostic,
 *      not a CTA screaming at the user.
 *   3. Click Review → expand inline to show each cluster: canonical on
 *      top, dupes below, total SRS cards the cleanup would remove.
 *   4. Click "Remove duplicates" → confirm inline → POST cleanup endpoint.
 *      On success, refetch preview (now empty) + notify the parent so the
 *      Library list refetches.
 *
 * Intentional design choices:
 *   - No modal. Inline confirm replaces the primary button for 3 seconds
 *     with Confirm / Cancel — same pattern as Manage Cards.
 *   - Amber is reserved; this uses `danger` tone for the destructive
 *     action and tertiary mono for the row details so the page doesn't
 *     shout.
 *   - The panel collapses by default after cleanup so the Library header
 *     stays tidy if the user returns to the view later.
 */
export function DuplicateCleanupPanel({ onCleanupComplete }: DuplicateCleanupPanelProps) {
  const [preview, setPreview] = useState<DuplicatePreview | null>(null);
  const [expanded, setExpanded] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshPreview = useCallback(async () => {
    try {
      const data = await library.duplicates();
      setPreview(data);
      setError(null);
    } catch (caught) {
      setError((caught as Error).message);
    }
  }, []);

  useEffect(() => {
    void refreshPreview();
  }, [refreshPreview]);

  const runCleanup = async () => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await library.cleanupDuplicates();
      await refreshPreview();
      setConfirming(false);
      setExpanded(false);
      onCleanupComplete();
    } catch (caught) {
      setError((caught as Error).message);
    } finally {
      setBusy(false);
    }
  };

  if (!preview || preview.total_groups === 0) {
    return null;
  }

  return (
    <Card padding="md" className={styles.panel}>
      <Stack gap={3}>
        <Stack direction="horizontal" className={styles.header} gap={3} wrap>
          <Stack direction="horizontal" gap={2}>
            <Badge tone="warning">Duplicates</Badge>
            <Text>
              <strong>{preview.total_duplicates}</strong> duplicate
              {preview.total_duplicates === 1 ? "" : "s"} across{" "}
              <strong>{preview.total_groups}</strong> source
              {preview.total_groups === 1 ? "" : "s"}.
            </Text>
          </Stack>
          <Stack direction="horizontal" gap={2}>
            <Button
              variant="ghost"
              onClick={() => setExpanded((prev) => !prev)}
              leadingIcon={
                <Icon name={expanded ? "chevron-up" : "chevron-down"} />
              }
            >
              {expanded ? "Hide" : "Review"}
            </Button>
            {!confirming ? (
              <Button
                variant="secondary"
                onClick={() => setConfirming(true)}
                leadingIcon={<Icon name="trash" />}
                disabled={busy}
              >
                Remove duplicates
              </Button>
            ) : (
              <Stack direction="horizontal" gap={1}>
                <Button
                  variant="danger"
                  onClick={() => void runCleanup()}
                  disabled={busy}
                >
                  {busy
                    ? "Removing…"
                    : `Confirm delete ${preview.total_duplicates}`}
                </Button>
                <Button
                  variant="ghost"
                  onClick={() => setConfirming(false)}
                  disabled={busy}
                >
                  Cancel
                </Button>
              </Stack>
            )}
          </Stack>
        </Stack>

        <Text tone="secondary" variant="caption">
          Will delete {preview.total_duplicates} file
          {preview.total_duplicates === 1 ? "" : "s"} and{" "}
          {preview.total_cards_in_duplicates} attached flashcard
          {preview.total_cards_in_duplicates === 1 ? "" : "s"}. The earliest
          copy of each source is kept as the canonical.
        </Text>

        {error && (
          <Text tone="danger" variant="caption">
            {error}
          </Text>
        )}

        {/*
          Compact preview card — shows the first file pair inline without
          expanding the full review. Matches the dashboard-style duplicate
          banner pattern: one concrete example + "N items to merge" counter
          + a Review Details button for the full plan. When the user
          actually expands (`expanded`) we still show every cluster below.
        */}
        {preview.groups[0] && !expanded && (
          <div className={styles.previewCard}>
            <div className={styles.previewHeader}>
              <span className={styles.previewEyebrow}>Cleanup preview</span>
              <span className={styles.previewCount}>
                {preview.total_duplicates}{" "}
                {preview.total_duplicates === 1 ? "item" : "items"} to merge
              </span>
            </div>
            <div className={styles.previewPair}>
              <span className={styles.previewKeep}>
                {preview.groups[0].canonical.filename}
              </span>
              {preview.groups[0].duplicates[0] && (
                <span className={styles.previewRemove}>
                  {preview.groups[0].duplicates[0].filename}
                </span>
              )}
            </div>
          </div>
        )}

        {expanded && (
          <div className={styles.groupList}>
            {preview.groups.map((group) => (
              <DuplicateGroupRow key={group.source_hash} group={group} />
            ))}
          </div>
        )}

        {busy && <Spinner size={16} />}
      </Stack>
    </Card>
  );
}

function DuplicateGroupRow({ group }: { group: DuplicateGroup }) {
  return (
    <div className={styles.group}>
      <div className={styles.groupHeader}>
        <span className={styles.groupHash} aria-label="source hash">
          {group.source_hash.slice(0, 8)}
        </span>
        {group.total_cards > 0 && (
          <span className={styles.groupCards}>
            · {group.total_cards} attached card{group.total_cards === 1 ? "" : "s"}
          </span>
        )}
      </div>
      <div className={styles.row}>
        <span className={styles.rowTag}>keep</span>
        <span className={styles.rowName}>{group.canonical.filename}</span>
        <span className={styles.rowMeta}>
          {group.canonical.subject_name ?? "General"}
          {group.canonical.upload_date ? ` · ${group.canonical.upload_date}` : ""}
        </span>
      </div>
      {group.duplicates.map((duplicate) => (
        <div key={duplicate.id} className={[styles.row, styles.rowRemove].join(" ")}>
          <span className={[styles.rowTag, styles.rowTagRemove].join(" ")}>
            remove
          </span>
          <span className={styles.rowName}>{duplicate.filename}</span>
          <span className={styles.rowMeta}>
            {duplicate.subject_name ?? "General"}
            {duplicate.upload_date ? ` · ${duplicate.upload_date}` : ""}
          </span>
        </div>
      ))}
    </div>
  );
}
