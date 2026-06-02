import { useEffect, useState } from "preact/hooks";

import { Button, Card, Spinner, Stack, Text } from "@/design-system";
import { navigateTo } from "@/app/shell/useAppShell";
import { briefs as briefsApi, type BriefSummary } from "@/services/api/endpoints";

import styles from "./ShelfView.module.css";

/**
 * Cachet PR6a — the Shelf (mechanical half).
 *
 * Lists saved briefs from GET /api/briefs and lets the lawyer delete one of
 * their own. This is the plain, token-styled surface; the warm register, the
 * card craft, the ink seal, and opening a brief to re-hydrate the Verify view
 * are the operator-gated PR6b pass. Deliberately no green/amber and no
 * confidence numbers — the seal label is a quiet word, not a status light.
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
    // Re-hydrate the Verify view from this saved brief (no re-verify). The warm
    // card styling of this open affordance is the operator-gated PR6b craft pass.
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
          <Text tone="danger">{state.message}</Text>
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
        <Stack gap={2} className={styles.empty}>
          <Text variant="h3">No saved briefs yet</Text>
          <Text tone="secondary">
            Verify a draft, then save it to keep the checked record here.
          </Text>
        </Stack>
      </div>
    );
  }

  return (
    <div className={styles.shelf}>
      <ShelfHeader count={state.items.length} />
      <ul className={styles.list}>
        {state.items.map((brief) => (
          <li key={brief.id} className={styles.row}>
            <Card padding="md">
              <Stack direction="horizontal" justify="between" align="start" gap={4}>
                <Stack
                  gap={1}
                  className={styles.rowMain}
                  role="button"
                  tabIndex={0}
                  aria-label={`Open ${brief.title || "Untitled brief"}`}
                  onClick={() => openBrief(brief.id)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      openBrief(brief.id);
                    }
                  }}
                >
                  <Text variant="h3" weight="semibold">
                    {brief.title || "Untitled brief"}
                  </Text>
                  <Stack
                    direction="horizontal"
                    gap={3}
                    align="center"
                    wrap
                    className={styles.meta}
                  >
                    <span className={styles.seal} data-state={brief.seal_state}>
                      {brief.seal_state === "sealed" ? "Sealed" : "Unsealed"}
                    </span>
                    {formatSavedAt(brief.created_at) ? (
                      <Text variant="caption" tone="tertiary">
                        {formatSavedAt(brief.created_at)}
                      </Text>
                    ) : null}
                    <code className={styles.fingerprint}>
                      {shortFingerprint(brief.fingerprint)}
                    </code>
                  </Stack>
                </Stack>
                <div className={styles.actions}>
                  {confirmingId === brief.id ? (
                    <Stack direction="horizontal" gap={2} align="center">
                      <Text variant="caption" tone="secondary">
                        Delete?
                      </Text>
                      <Button
                        variant="danger"
                        size="sm"
                        isLoading={deletingId === brief.id}
                        onClick={() => void handleDelete(brief.id)}
                      >
                        Confirm
                      </Button>
                      <Button variant="ghost" size="sm" onClick={() => setConfirmingId(null)}>
                        Cancel
                      </Button>
                    </Stack>
                  ) : (
                    <Button variant="ghost" size="sm" onClick={() => setConfirmingId(brief.id)}>
                      Delete
                    </Button>
                  )}
                </div>
              </Stack>
            </Card>
          </li>
        ))}
      </ul>
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
      <Text as="h1" variant="h1">
        Shelf
      </Text>
      <Text tone="secondary">{subtitle}</Text>
    </header>
  );
}
