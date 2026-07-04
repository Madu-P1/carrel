import { useEffect, useState } from "preact/hooks";

import { Button, Icon, Spinner, Stack, Text } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";
import { briefs as briefsApi, type BriefSummary } from "@/services/api/endpoints";

import styles from "./ShelfView.module.css";

/**
 * The Shelf (handoff §8): a centered 860px list of saved briefs. Each row is a
 * hover-lift card — serif title, mono "date · fingerprint" meta, and a right
 * seal badge (SEAL INTACT / UNSEALED; a cracked seal is derived on reopen,
 * where the saved fingerprint meets the draft, so the list never claims it).
 * Opening a brief re-hydrates the Verify view from the stored response (no
 * re-verify). The two-step delete stays: a hard delete has no undo.
 */

type LoadState =
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "ready"; items: BriefSummary[] };

function formatSavedAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return "";
  return parsed.toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "numeric"
  });
}

function shortFingerprint(fingerprint: string): string {
  return fingerprint.length > 12 ? `${fingerprint.slice(0, 12)}…` : fingerprint;
}

export function ShelfView() {
  const [state, setState] = useState<LoadState>({ status: "loading" });
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [deletingId, setDeletingId] = useState<string | null>(null);

  async function load() {
    setState({ status: "loading" });
    try {
      const result = await briefsApi.list();
      setState({ status: "ready", items: result.briefs ?? [] });
    } catch (err) {
      setState({
        status: "error",
        message: err instanceof Error ? err.message : "Could not load the Shelf."
      });
    }
  }

  useEffect(() => {
    void load();
  }, []);

  function openBrief(id: string) {
    // Re-hydrate the Verify view from this saved brief (no re-verify).
    navigateTo(`/verify?brief=${encodeURIComponent(id)}`);
  }

  async function handleDelete(id: string) {
    setDeletingId(id);
    try {
      await briefsApi.remove(id);
      setState((prev) =>
        prev.status === "ready"
          ? { status: "ready", items: prev.items.filter((brief) => brief.id !== id) }
          : prev
      );
      setConfirmingId(null);
    } catch {
      // The row stays; reload so the list reflects server truth.
      await load();
    } finally {
      setDeletingId(null);
    }
  }

  if (state.status === "loading") {
    return (
      <div className={styles.shelf}>
        <Stack align="center" gap={3} className={styles.centered}>
          <Spinner label="Loading saved briefs" />
        </Stack>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.shelf}>
        <Stack gap={3} align="start" className={styles.centered}>
          <Text tone="secondary">{state.message}</Text>
          <Button variant="secondary" onClick={() => void load()}>
            Reload the Shelf
          </Button>
        </Stack>
      </div>
    );
  }

  if (state.items.length === 0) {
    return (
      <div className={styles.shelf}>
        <div className={styles.empty}>
          <h2 className={styles.emptyTitle}>Nothing on the shelf yet</h2>
          <p className={styles.emptyBody}>
            Verify a draft, then seal it to keep the checked record here.
          </p>
        </div>
      </div>
    );
  }

  const renderRow = (brief: BriefSummary) => {
    const isSealed = brief.seal_state === "sealed";
    const date = formatSavedAt(brief.created_at);
    const title = brief.title || "Untitled brief";
    return (
      <li key={brief.id} className={styles.row} data-sealed={isSealed ? "true" : "false"}>
        <div
          className={styles.rowMain}
          role="button"
          tabIndex={0}
          aria-label={`Open ${title}`}
          onClick={() => openBrief(brief.id)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              openBrief(brief.id);
            }
          }}
        >
          <span className={styles.title}>{title}</span>
          <span className={styles.meta}>
            {date ? <span>{date}</span> : null}
            {date ? (
              <span className={styles.dot} aria-hidden="true">
                ·
              </span>
            ) : null}
            <code className={styles.fingerprint}>{shortFingerprint(brief.fingerprint)}</code>
          </span>
        </div>
        <div className={styles.right}>
          <span className={styles.sealBadge} data-sealed={isSealed ? "true" : "false"}>
            {isSealed ? "SEAL INTACT" : "UNSEALED"}
          </span>
          {confirmingId === brief.id ? (
            // Armed: keep the two-step confirm (a hard delete has no undo).
            <span className={styles.confirm}>
              <Text variant="caption" tone="secondary">
                Delete?
              </Text>
              <Button
                variant="secondary"
                size="sm"
                isLoading={deletingId === brief.id}
                onClick={() => void handleDelete(brief.id)}
              >
                Confirm
              </Button>
              <Button variant="ghost" size="sm" onClick={() => setConfirmingId(null)}>
                Cancel
              </Button>
            </span>
          ) : (
            <button
              type="button"
              className={styles.binBtn}
              aria-label={`Delete ${title}`}
              onClick={() => setConfirmingId(brief.id)}
            >
              <Icon name="trash" />
            </button>
          )}
        </div>
      </li>
    );
  };

  return (
    <div className={styles.shelf}>
      <ul className={styles.list}>{state.items.map(renderRow)}</ul>
      <p className={styles.reopenNote}>
        Reopening a brief re-reads the saved record. If the draft no longer matches its
        fingerprint, the seal shows as cracked.
      </p>
    </div>
  );
}
