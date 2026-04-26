import { useCallback, useEffect, useMemo, useState } from "preact/hooks";

import { Badge, Button, Card, Icon, Input, Spinner, Stack, Text, toast } from "@/design-system";
import {
  study,
  type SrsCard,
  type SrsListParams,
  type SrsSubjectSummary
} from "@/services/api/endpoints";

import { CardAiDraftDialog } from "./CardAiDraftDialog";
import { CardCreateDialog } from "./CardCreateDialog";
import styles from "./ManageCardsView.module.css";

/**
 * Manage Cards — the curation surface on top of the SRS library.
 *
 * Why it exists: the ingestion pipeline occasionally produces filler cards
 * (heading echoes, "What does the source say about X"-style fronts). The
 * review flow has no way to say "this card is garbage, never show me again."
 * This view gives the user subject-level triage, search, inline delete, and
 * bulk selection so a library of 800+ cards stays curatable in minutes.
 *
 * Design notes:
 *   - No modal on delete. Inline confirm replaces the delete button for 3s.
 *     A modal would dam the one-per-second flow of culling bad cards.
 *   - Paged at 50 per request. Keeps SQLite, the network, and the renderer
 *     all on easy mode; the Load more button fetches the next page.
 *   - Search is server-side LIKE on front/back. FTS5 is a follow-up once
 *     libraries grow past ~10k cards.
 */

const PAGE_SIZE = 50;

interface DeleteState {
  kind: "idle" | "confirming" | "pending";
  cardId: string | null;
}

export function ManageCardsView() {
  const [subjects, setSubjects] = useState<SrsSubjectSummary[] | null>(null);
  const [subjectsError, setSubjectsError] = useState<string | null>(null);
  const [subject, setSubject] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [searchDraft, setSearchDraft] = useState("");
  const [cards, setCards] = useState<SrsCard[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const [deleteState, setDeleteState] = useState<DeleteState>({ kind: "idle", cardId: null });
  const [bulkPending, setBulkPending] = useState(false);
  const [createOpen, setCreateOpen] = useState(false);
  const [aiDraftOpen, setAiDraftOpen] = useState(false);

  const refreshSubjects = useCallback(async () => {
    try {
      const data = await study.subjects();
      setSubjects(data.subjects);
      setSubjectsError(null);
    } catch (error) {
      setSubjectsError((error as Error).message);
    }
  }, []);

  const loadPage = useCallback(
    async (nextOffset: number, params: SrsListParams) => {
      setLoading(true);
      setLoadError(null);
      try {
        const data = await study.listCards({
          ...params,
          limit: PAGE_SIZE,
          offset: nextOffset
        });
        setCards((prev) => (nextOffset === 0 ? data.cards : [...prev, ...data.cards]));
        setTotal(data.total);
        setOffset(nextOffset + data.cards.length);
      } catch (error) {
        setLoadError((error as Error).message);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  // Initial fetch + reload on filter change. Filters bust the page offset.
  useEffect(() => {
    void refreshSubjects();
  }, [refreshSubjects]);

  useEffect(() => {
    setSelection(new Set());
    void loadPage(0, {
      subject: subject ?? undefined,
      search: search || undefined
    });
  }, [subject, search, loadPage]);

  const handleDelete = async (cardId: string) => {
    setDeleteState({ kind: "pending", cardId });
    try {
      await study.deleteCard(cardId);
      setCards((prev) => prev.filter((c) => c.id !== cardId));
      setSelection((prev) => {
        const next = new Set(prev);
        next.delete(cardId);
        return next;
      });
      setTotal((t) => Math.max(0, t - 1));
      // Keep `offset` (the count of rows already pulled from the server)
      // in sync with the visible row count so the next "Load more" doesn't
      // duplicate or skip cards. The deleted row was inside the prefix we
      // already paged in, so the next request should advance from one row
      // earlier on the server timeline.
      setOffset((o) => Math.max(0, o - 1));
      setDeleteState({ kind: "idle", cardId: null });
      // Subject counts may have shifted if we emptied a bucket. Cheap refresh.
      void refreshSubjects();
      toast.info("Card deleted");
    } catch (error) {
      setLoadError((error as Error).message);
      setDeleteState({ kind: "idle", cardId: null });
      toast.error("Delete failed", (error as Error).message);
    }
  };

  const handleCardCreated = (card: SrsCard) => {
    // CardCreateDialog explicitly saves orphan cards (no subject). When
    // the user is filtered to a specific subject, the new orphan does
    // NOT match the current view's contract — prepending it would leak a
    // non-matching row into a filtered list until the next reload.
    //
    // In that case, bump total + refresh subject counts only, and tell
    // the user where the card actually lives. The unfiltered "All
    // subjects" view remains the reachable destination.
    if (subject !== null) {
      setTotal((t) => t + 1);
      void refreshSubjects();
      toast.success(
        "Card saved under All subjects",
        "Switch to All subjects to see it; or attach a subject from Library first.",
      );
      return;
    }
    // No filter active — prepend optimistically so the user sees their new
    // card immediately. Bumping `offset` alongside the cards array keeps
    // the "Load more" boundary aligned with the new visible row count.
    setCards((prev) => [card, ...prev]);
    setTotal((t) => t + 1);
    setOffset((o) => o + 1);
    void refreshSubjects();
    toast.success("Card saved", "It's queued for your next review session.");
  };

  const handleAiCardsCreated = (created: SrsCard[]) => {
    if (created.length === 0) return;
    // AI-drafted cards are also orphan-on-create. Apply the same filter
    // gate so a subject-filtered list doesn't suddenly show non-matching
    // rows after a draft batch.
    if (subject !== null) {
      setTotal((t) => t + created.length);
      void refreshSubjects();
      toast.success(
        `${created.length} card${created.length === 1 ? "" : "s"} saved under All subjects`,
        "Switch to All subjects to see them; or attach a subject from Library first.",
      );
      return;
    }
    setCards((prev) => [...created, ...prev]);
    setTotal((t) => t + created.length);
    setOffset((o) => o + created.length);
    void refreshSubjects();
    toast.success(
      `${created.length} card${created.length === 1 ? "" : "s"} saved`,
      "Review them from the top of this list, or start a session to see them immediately."
    );
  };

  const handleBulkDelete = async () => {
    if (selection.size === 0 || bulkPending) return;
    setBulkPending(true);
    const ids = Array.from(selection);
    try {
      await study.bulkDeleteCards(ids);
      const idSet = new Set(ids);
      setCards((prev) => prev.filter((c) => !idSet.has(c.id)));
      setSelection(new Set());
      setTotal((t) => Math.max(0, t - ids.length));
      // See handleDelete — keep `offset` aligned with visible row count
      // so subsequent "Load more" requests target the correct slice.
      setOffset((o) => Math.max(0, o - ids.length));
      void refreshSubjects();
      toast.info(`${ids.length} card${ids.length === 1 ? "" : "s"} deleted`);
    } catch (error) {
      setLoadError((error as Error).message);
      toast.error("Bulk delete failed", (error as Error).message);
    } finally {
      setBulkPending(false);
    }
  };

  const toggleSelect = (cardId: string) => {
    setSelection((prev) => {
      const next = new Set(prev);
      if (next.has(cardId)) next.delete(cardId);
      else next.add(cardId);
      return next;
    });
  };

  const toggleSelectAllVisible = () => {
    setSelection((prev) => {
      const allSelected = cards.every((c) => prev.has(c.id));
      if (allSelected) {
        const next = new Set(prev);
        cards.forEach((c) => next.delete(c.id));
        return next;
      }
      const next = new Set(prev);
      cards.forEach((c) => next.add(c.id));
      return next;
    });
  };

  const hasMore = cards.length < total;
  const visibleAllSelected = cards.length > 0 && cards.every((c) => selection.has(c.id));

  const activeSubjectLabel = useMemo(() => {
    if (!subject) return "All subjects";
    return subject;
  }, [subject]);

  return (
    <div className={styles.wrap}>
      <Stack gap={5}>
        <Stack direction="horizontal" className={styles.titleRow} gap={4}>
          <Stack gap={3} className={styles.titleCopy}>
            <Badge tone="info">Manage cards</Badge>
            <Text as="h2" variant="display" weight="bold">
              Curate your library of flashcards.
            </Text>
            <Text tone="secondary">
              Filter by subject, search front or back text, and delete cards the
              ingestion pipeline got wrong. Bulk select for quick passes.
            </Text>
          </Stack>
          <div className={styles.titleActions}>
            <Button
              leadingIcon={<Icon name="sparkle" />}
              onClick={() => setAiDraftOpen(true)}
              variant="secondary"
            >
              Draft from a topic
            </Button>
            <Button
              leadingIcon={<Icon name="plus" />}
              onClick={() => setCreateOpen(true)}
            >
              New card
            </Button>
          </div>
        </Stack>

        <Card padding="lg">
          <Stack gap={4}>
            {/* Subject filter chips — always show an "All" chip plus one per subject. */}
            <Stack direction="horizontal" className={styles.chipRow} gap={2} wrap>
              <button
                type="button"
                className={[
                  styles.subjectChip,
                  subject === null ? styles.subjectChipActive : ""
                ].join(" ")}
                onClick={() => setSubject(null)}
              >
                <span>All</span>
                {subjects && (
                  <span className={styles.chipCount}>
                    {subjects.reduce((sum, s) => sum + s.card_count, 0)}
                  </span>
                )}
              </button>
              {(subjects ?? []).map((s) => (
                <button
                  key={s.subject_name}
                  type="button"
                  className={[
                    styles.subjectChip,
                    subject === s.subject_name ? styles.subjectChipActive : ""
                  ].join(" ")}
                  onClick={() => setSubject(s.subject_name)}
                >
                  <span>{s.subject_name}</span>
                  <span className={styles.chipCount}>{s.card_count}</span>
                  {s.due_count > 0 && (
                    <span className={styles.chipDue} aria-label={`${s.due_count} due`}>
                      · {s.due_count} due
                    </span>
                  )}
                </button>
              ))}
              {subjectsError && (
                <Text tone="secondary" variant="caption">
                  Could not load subjects: {subjectsError}
                </Text>
              )}
            </Stack>

            <form
              className={styles.searchRow}
              onSubmit={(event) => {
                event.preventDefault();
                setSearch(searchDraft.trim());
              }}
            >
              <Input
                className={styles.searchField}
                label="Search"
                helpText="Matches card front or back. Press enter to apply."
                placeholder="checkpoints, capital markets, etc."
                value={searchDraft}
                onInput={(event) => {
                  setSearchDraft((event.currentTarget as HTMLInputElement).value);
                }}
              />
              <Stack direction="horizontal" gap={2}>
                <Button type="submit" variant="secondary">
                  Apply
                </Button>
                {search && (
                  <Button
                    type="button"
                    variant="ghost"
                    onClick={() => {
                      setSearchDraft("");
                      setSearch("");
                    }}
                  >
                    Clear
                  </Button>
                )}
              </Stack>
            </form>

            <Stack direction="horizontal" className={styles.toolbar} gap={3} wrap>
              <Text tone="secondary" variant="caption">
                {loading
                  ? "Loading…"
                  : `Showing ${cards.length} of ${total} · ${activeSubjectLabel}`}
              </Text>
              <Stack direction="horizontal" gap={2}>
                {cards.length > 0 && (
                  <Button variant="ghost" onClick={toggleSelectAllVisible}>
                    {visibleAllSelected ? "Deselect visible" : "Select visible"}
                  </Button>
                )}
                {selection.size > 0 && (
                  <Button
                    variant="secondary"
                    disabled={bulkPending}
                    onClick={() => void handleBulkDelete()}
                    leadingIcon={<Icon name="trash" />}
                  >
                    {bulkPending ? "Deleting…" : `Delete ${selection.size} selected`}
                  </Button>
                )}
              </Stack>
            </Stack>

            {loadError && (
              <Stack gap={2}>
                <Badge tone="danger">Request failed</Badge>
                <Text tone="secondary">{loadError}</Text>
              </Stack>
            )}

            <div className={styles.list}>
              {cards.length === 0 && !loading ? (
                <div className={styles.empty}>
                  <Stack gap={3}>
                    <Text>
                      No cards match this filter. Widen the subject or
                      clear the search.
                    </Text>
                    <Stack direction="horizontal" gap={2}>
                      <Button
                        onClick={() => {
                          setSubject(null);
                          setSearch("");
                          setSearchDraft("");
                        }}
                        variant="secondary"
                      >
                        Clear filters
                      </Button>
                    </Stack>
                  </Stack>
                </div>
              ) : null}

              {cards.map((card) => (
                <CardRow
                  key={card.id}
                  card={card}
                  selected={selection.has(card.id)}
                  deleteState={deleteState.cardId === card.id ? deleteState.kind : "idle"}
                  onToggleSelect={() => toggleSelect(card.id)}
                  onBeginDelete={() =>
                    setDeleteState({ kind: "confirming", cardId: card.id })
                  }
                  onCancelDelete={() => setDeleteState({ kind: "idle", cardId: null })}
                  onConfirmDelete={() => void handleDelete(card.id)}
                />
              ))}
            </div>

            <Stack direction="horizontal" className={styles.footer} gap={3}>
              {hasMore && (
                <Button
                  variant="secondary"
                  disabled={loading}
                  onClick={() =>
                    void loadPage(offset, {
                      subject: subject ?? undefined,
                      search: search || undefined
                    })
                  }
                >
                  {loading ? "Loading…" : `Load ${Math.min(PAGE_SIZE, total - cards.length)} more`}
                </Button>
              )}
              {loading && <Spinner size={16} />}
            </Stack>
          </Stack>
        </Card>
      </Stack>

      <CardCreateDialog
        activeSubject={subject}
        onClose={() => setCreateOpen(false)}
        onCreated={handleCardCreated}
        open={createOpen}
      />

      <CardAiDraftDialog
        onCardsCreated={handleAiCardsCreated}
        onClose={() => setAiDraftOpen(false)}
        open={aiDraftOpen}
      />
    </div>
  );
}

interface CardRowProps {
  card: SrsCard;
  selected: boolean;
  deleteState: DeleteState["kind"];
  onToggleSelect: () => void;
  onBeginDelete: () => void;
  onCancelDelete: () => void;
  onConfirmDelete: () => void;
}

function CardRow({
  card,
  selected,
  deleteState,
  onToggleSelect,
  onBeginDelete,
  onCancelDelete,
  onConfirmDelete
}: CardRowProps) {
  return (
    <div
      className={[styles.row, selected ? styles.rowSelected : ""].join(" ")}
      aria-selected={selected}
    >
      <label className={styles.selectCell}>
        <input
          type="checkbox"
          checked={selected}
          onChange={onToggleSelect}
          aria-label={`Select card: ${card.front}`}
        />
      </label>
      <div className={styles.content}>
        <div className={styles.meta}>
          <span className={styles.metaToken}>{card.subject_name ?? "General"}</span>
          <span className={styles.metaSep}>·</span>
          <span className={styles.metaToken}>{card.document_name}</span>
          <span className={styles.metaSep}>·</span>
          <span className={styles.metaToken}>{card.concept}</span>
          {card.due_date && (
            <>
              <span className={styles.metaSep}>·</span>
              <span className={styles.metaToken}>due {card.due_date}</span>
            </>
          )}
        </div>
        <div className={styles.front}>{card.front}</div>
        <div className={styles.back}>{card.back}</div>
      </div>
      <div className={styles.actions}>
        {deleteState === "idle" && (
          <button
            type="button"
            className={styles.deleteBtn}
            onClick={onBeginDelete}
            aria-label={`Delete card: ${card.front}`}
          >
            <Icon name="trash" size={16} />
            <span>Delete</span>
          </button>
        )}
        {deleteState === "confirming" && (
          <div className={styles.confirmGroup}>
            <button
              type="button"
              className={styles.confirmBtn}
              onClick={onConfirmDelete}
            >
              Confirm
            </button>
            <button
              type="button"
              className={styles.cancelBtn}
              onClick={onCancelDelete}
            >
              Cancel
            </button>
          </div>
        )}
        {deleteState === "pending" && (
          <Text tone="secondary" variant="caption">
            Deleting…
          </Text>
        )}
      </div>
    </div>
  );
}
