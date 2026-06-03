import { useEffect, useState } from "preact/hooks";

import { Button, Icon, Spinner, Stack, Text } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";
import { briefs as briefsApi, type BriefSummary } from "@/services/api/endpoints";

import styles from "./ShelfView.module.css";

/**
 * Cachet PR6b-craft — the Shelf (warm register, Direction C "The Spine").
 *
 * A bookshelf of saved briefs: grouped by the human's act (Sealed / Unsealed),
 * each a row with a gutter spine (ink when sealed) and an ink seal disc that
 * echoes the certification seal. Warm cream ground, a Fraunces ceremonial
 * title. No oxblood (reserved for verify flags), no green/amber, no verdict
 * signal — warmth never touches a verdict. The open + delete wiring is PR6b
 * mechanical; this pass is the craft. Opening a brief re-hydrates the Verify
 * view from the stored response (no re-verify).
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

/** The ink seal disc — echoes the cert seal (PR2): an ink ring + engraved
 *  core. Decorative; the "Sealed" section label carries the meaning. */
function SealDisc() {
  return (
    <span className={styles.seal} aria-hidden="true">
      <svg viewBox="0 0 18 18">
        <circle className={styles.sealRing} cx="9" cy="9" r="7" />
        <circle className={styles.sealCore} cx="9" cy="9" r="3" />
      </svg>
    </span>
  );
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
        <ShelfHeader />
        <Stack align="center" gap={3} className={styles.centered}>
          <Spinner label="Loading saved briefs" />
        </Stack>
      </div>
    );
  }

  if (state.status === "error") {
    return (
      <div className={styles.shelf}>
        <ShelfHeader />
        <Stack gap={3} align="start" className={styles.centered}>
          <Text tone="secondary">{state.message}</Text>
          <Button variant="secondary" onClick={() => void load()}>
            Try again
          </Button>
        </Stack>
      </div>
    );
  }

  if (state.items.length === 0) {
    return (
      <div className={styles.shelf}>
        <ShelfHeader />
        <div className={styles.empty}>
          <h2 className={styles.emptyTitle}>Nothing on the shelf yet</h2>
          <p className={styles.emptyBody}>
            Verify a draft, then seal it to keep the checked record here.
          </p>
        </div>
      </div>
    );
  }

  const sealed = state.items.filter((brief) => brief.seal_state === "sealed");
  const unsealed = state.items.filter((brief) => brief.seal_state !== "sealed");

  const renderRow = (brief: BriefSummary) => {
    const isSealed = brief.seal_state === "sealed";
    const date = formatSavedAt(brief.created_at);
    const title = brief.title || "Untitled brief";
    return (
      <li key={brief.id} className={styles.spine} data-sealed={isSealed ? "true" : "false"}>
        <span className={styles.gutter} aria-hidden="true">
          <span className={styles.bar} />
        </span>
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
          {isSealed ? <SealDisc /> : null}
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
      <ShelfHeader count={state.items.length} />
      {sealed.length > 0 ? (
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Sealed</h2>
          <ul className={styles.list}>{sealed.map(renderRow)}</ul>
        </section>
      ) : null}
      {unsealed.length > 0 ? (
        <section className={styles.section}>
          <h2 className={styles.sectionLabel}>Unsealed</h2>
          <ul className={styles.list}>{unsealed.map(renderRow)}</ul>
        </section>
      ) : null}
    </div>
  );
}

function ShelfHeader({ count }: { count?: number }) {
  const subtitle =
    typeof count === "number" && count > 0
      ? `${count} saved ${count === 1 ? "brief" : "briefs"}`
      : "Saved briefs";
  return (
    <header className={styles.header}>
      <h1 className={styles.pageTitle}>Shelf</h1>
      <p className={styles.subtitle}>{subtitle}</p>
    </header>
  );
}
