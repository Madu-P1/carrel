import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Button, Card, Icon, Input, Stack, Text } from "@/design-system";
import { library, type DocumentRow as DocumentRowType } from "@/services/api/endpoints";
import { events } from "@/services/metrics/events";

import { DeleteConfirmDialog } from "./components/DeleteConfirmDialog";
import { DocumentRow } from "./components/DocumentRow";
import { DuplicateCleanupPanel } from "./components/DuplicateCleanupPanel";
import { ImportDropzone } from "./components/ImportDropzone";
import { LibraryEmptyState } from "./components/LibraryEmptyState";
import { LibraryErrorState } from "./components/LibraryErrorState";
import { SubjectCardGrid } from "./components/SubjectCardGrid";
import { SubjectSection } from "./components/SubjectSection";
import { useDeleteDocument } from "./hooks/useDeleteDocument";
import { useDocumentsQuery } from "./hooks/useDocumentsQuery";
import styles from "./LibraryView.module.css";
import { groupBySubject } from "./utils/group-by-subject";

// Lowercase-substring match across filename + subject_name. Intentionally
// dumb and allocation-light so a 2000-doc library stays snappy without a trie.
function matchesDocument(doc: DocumentRowType, needle: string): boolean {
  const title = (doc.filename ?? "").toLowerCase();
  const subject = (doc.subject_name ?? "").toLowerCase();
  return title.includes(needle) || subject.includes(needle);
}

function LibrarySkeleton() {
  return (
    <div className={styles.skeleton}>
      <div className={styles.skeletonCard} />
      <div className={styles.skeletonCard} />
    </div>
  );
}

/**
 * Library home.
 *
 * Structure:
 *   - Header: page title + import dropzone
 *   - Search: always visible, filters to a flat result list when active
 *   - Duplicate cleanup banner (renders itself only when dupes exist)
 *   - Subject card grid — the at-a-glance dashboard of active study
 *     territories. This is the "home" the user lands on.
 *   - Drill-down panel — when a subject card is clicked, the file list
 *     for just that subject renders below the grid with a "Back to all
 *     subjects" button. When nothing's selected, no files are shown —
 *     the dashboard is the whole view.
 *
 * The bump counter (`mutationKey`) is passed to the grid so it refetches
 * after the doc list changes (upload, delete, cleanup).
 */
export function LibraryView() {
  const { data, loading, error, refetch } = useDocumentsQuery();
  const [openSubject, setOpenSubject] = useState<string | null>(null);
  const [mutationKey, setMutationKey] = useState(0);
  const [query, setQuery] = useState("");
  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const searchTrackedRef = useRef(false);
  const { deleteDocument } = useDeleteDocument();

  const documents = data.value ?? [];
  const groups = groupBySubject(documents);
  const drillInRef = useRef<HTMLDivElement | null>(null);

  // When the user drills into a subject, scroll the panel into view so the
  // pop animation actually happens where their eyes are. Without this, the
  // panel mounts below the subject grid (often below the fold), the
  // 320ms pop fires off-screen, and the user only sees the static end
  // state once they manually scroll down — reading as "no animation."
  //
  // Reduced-motion users get an instant scroll instead of "smooth" so we
  // don't induce motion they've opted out of.
  useEffect(() => {
    if (!openSubject) return;
    const el = drillInRef.current;
    if (!el || typeof el.scrollIntoView !== "function") return;
    const reduce =
      typeof window !== "undefined" &&
      window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({
      behavior: reduce ? "auto" : "smooth",
      block: "start",
    });
  }, [openSubject]);

  const bumpMutationKey = () => setMutationKey((k) => k + 1);
  const refreshAll = () => {
    void refetch();
    bumpMutationKey();
  };

  const openSubjectRows = openSubject ? groups[openSubject] ?? [] : [];
  const subjectOptions = Object.keys(groups).sort((a, b) => a.localeCompare(b));

  const trimmed = query.trim();
  const isSearching = trimmed.length > 0;
  const results = useMemo(() => {
    if (!isSearching) return [];
    const needle = trimmed.toLowerCase();
    return documents.filter((doc) => matchesDocument(doc, needle));
    // documents is a fresh ref on every render; gating on length + query + mutationKey
    // keeps the memo stable for typical typing without walking the array each keystroke.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [documents.length, trimmed, mutationKey]);

  useEffect(() => {
    if (!isSearching) {
      searchTrackedRef.current = false;
      return;
    }
    if (searchTrackedRef.current) return;
    searchTrackedRef.current = true;
    void events.track("library.search_used", {
      library_size: documents.length,
      result_count: results.length
    }, "library");
  }, [documents.length, isSearching, results.length]);

  // Note: we don't bind `/` to focus this input because AppShell already
  // owns `/` as "jump to Ask." The search bar is reached via mouse or by
  // tabbing into it from the dropzone. If discoverability becomes a real
  // concern, a Cmd+K palette entry is the next step, not a keybind fight.

  const [deleteTarget, setDeleteTarget] = useState<DocumentRowType | null>(null);
  const [deleteError, setDeleteError] = useState<Error | null>(null);
  const [deleteLoading, setDeleteLoading] = useState(false);

  const handleResultDelete = (doc: DocumentRowType) => {
    setDeleteTarget(doc);
    setDeleteError(null);
  };

  const confirmDelete = () => {
    if (!deleteTarget) return;
    setDeleteLoading(true);
    setDeleteError(null);
    deleteDocument(deleteTarget.id)
      .then(() => {
        setDeleteTarget(null);
        refreshAll();
      })
      .catch((err: Error) => {
        setDeleteError(err);
      })
      .finally(() => {
        setDeleteLoading(false);
      });
  };

  const closeDeleteDialog = () => {
    if (deleteLoading) return;
    setDeleteTarget(null);
    setDeleteError(null);
  };

  return (
    <Stack className={styles.container} gap={6}>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <span className={styles.eyebrow}>Source library</span>
          <h1 className={styles.heading}>Your sources.</h1>
          <Text tone="secondary">
            Source-grounded documents, grouped by subject. Import to add
            material; click any subject to drill into its files.
          </Text>
        </div>
        <ImportDropzone
          onSubjectCreated={async (subjectName) => {
            await library.createSubject(subjectName);
            refreshAll();
          }}
          onUploaded={refreshAll}
          subjectOptions={subjectOptions}
        />
      </header>

      {data.value && data.value.length > 0 ? (
        <div className={styles.searchRow}>
          <Input
            aria-label="Search library by title or subject"
            leadingIcon={<Icon name="search" />}
            onInput={(e) => setQuery((e.currentTarget as HTMLInputElement).value)}
            placeholder="Search your library by title or subject."
            ref={searchInputRef}
            type="search"
            value={query}
          />
          <div aria-live="polite" className={styles.searchCount}>
            {isSearching ? (
              <Text tone="tertiary" variant="caption">
                {results.length} match{results.length === 1 ? "" : "es"}
              </Text>
            ) : null}
          </div>
        </div>
      ) : null}

      {loading.value && !data.value ? <LibrarySkeleton /> : null}
      {error.value ? <LibraryErrorState error={error.value} onRetry={() => void refetch()} /> : null}
      {data.value && data.value.length === 0 ? <LibraryEmptyState onDemoLoaded={refreshAll} /> : null}

      {data.value && data.value.length > 0 && !isSearching ? (
        <DuplicateCleanupPanel onCleanupComplete={refreshAll} />
      ) : null}

      {/* Search results: flat list of filtered documents. Keeps DocumentRow
        identical to subject views so hover, click-to-flight, and delete
        behavior stay consistent. Empty state speaks to the user directly. */}
      {isSearching ? (
        <Stack gap={3}>
          <Text as="h3" variant="h3" weight="semibold">
            Search results
          </Text>
          {results.length === 0 ? (
            <Card padding="md">
              <Stack gap={3}>
                <Text tone="secondary">
                  No documents match &ldquo;{trimmed}&rdquo;.
                </Text>
                <Text tone="tertiary" variant="caption">
                  Try a shorter phrase, a subject name, or clear the search to browse all subjects.
                </Text>
                <Stack direction="horizontal" gap={2}>
                  <Button onClick={() => setQuery("")} variant="secondary">
                    Clear the search
                  </Button>
                </Stack>
              </Stack>
            </Card>
          ) : (
            <div className={styles.resultsList}>
              {results.map((doc) => (
                <DocumentRow
                  document={doc}
                  key={doc.id}
                  onDelete={() => handleResultDelete(doc)}
                  onOpen={() => navigateTo(`/reader/${doc.id}`)}
                />
              ))}
            </div>
          )}
        </Stack>
      ) : null}

      {/*
        Subject dashboard — the Library home. When the user clicks into a
        subject, we render that subject's file list below with a breadcrumb
        back. The grid itself stays visible so comparing subjects is one
        click away. Suppressed during an active search to reduce noise.
      */}
      {data.value && !isSearching ? (
        <SubjectCardGrid
          onSubjectOpen={(subject) => setOpenSubject(subject)}
          refreshKey={mutationKey}
        />
      ) : null}

      {openSubject && !isSearching ? (
        // `key={openSubject}` remounts the block when the user switches
        // subjects, which replays the pop animation per drill-in. The
        // `.drillInWrap` class owns the animation itself.
        //
        // The ref is bound here so the scroll-into-view effect above can
        // anchor the viewport on the panel as it pops, ensuring the
        // animation lands inside the visible area instead of below the
        // fold.
        <div className={styles.drillInWrap} key={openSubject} ref={drillInRef}>
          <Stack gap={3}>
            <Stack direction="horizontal" gap={2}>
              <Button
                variant="ghost"
                onClick={() => setOpenSubject(null)}
                leadingIcon={<Icon name="chevron-left" />}
              >
                Back to all subjects
              </Button>
              <Text tone="secondary">
                {openSubject} · {openSubjectRows.length} document
                {openSubjectRows.length === 1 ? "" : "s"}
              </Text>
            </Stack>
            <SubjectSection
              documents={openSubjectRows}
              onDocumentDeleted={refreshAll}
              onSubjectRenamed={(nextSubject) => {
                // Move the drill-in pointer to the new name BEFORE the
                // refetch lands. Otherwise `groups[openSubject]` is empty
                // (the rows now live under the new subject key) and the
                // panel shows a blank list under the stale label until
                // the user hits "Back to all subjects."
                if (nextSubject !== openSubject) {
                  setOpenSubject(nextSubject);
                }
                refreshAll();
              }}
              subject={openSubject}
            />
          </Stack>
        </div>
      ) : null}

      {data.value && data.value.length > 0 && !openSubject && !isSearching ? (
        <Card padding="md">
          <Text tone="tertiary">
            {data.value.length} documents indexed across{" "}
            {Object.keys(groups).length} subjects.
          </Text>
        </Card>
      ) : null}

      <DeleteConfirmDialog
        documentName={deleteTarget?.filename ?? "this source"}
        error={deleteError}
        loading={deleteLoading}
        onClose={closeDeleteDialog}
        onConfirm={confirmDelete}
        open={deleteTarget !== null}
      />
    </Stack>
  );
}
