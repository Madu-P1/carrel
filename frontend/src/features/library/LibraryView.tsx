import { useMemo, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Badge, Button, Card, Icon, Input, Stack, Text } from "@/design-system";
import type { DocumentRow as DocumentRowType } from "@/services/api/endpoints";

import { groupBySubject } from "./utils/group-by-subject";
import { useDocumentsQuery } from "./hooks/useDocumentsQuery";
import { useDeleteDocument } from "./hooks/useDeleteDocument";
import { DocumentRow } from "./components/DocumentRow";
import { DuplicateCleanupPanel } from "./components/DuplicateCleanupPanel";
import { ImportDropzone } from "./components/ImportDropzone";
import { LibraryEmptyState } from "./components/LibraryEmptyState";
import { LibraryErrorState } from "./components/LibraryErrorState";
import { SubjectCardGrid } from "./components/SubjectCardGrid";
import { SubjectSection } from "./components/SubjectSection";
import styles from "./LibraryView.module.css";

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
  const { deleteDocument } = useDeleteDocument();

  const documents = data.value ?? [];
  const groups = groupBySubject(documents);

  const bumpMutationKey = () => setMutationKey((k) => k + 1);
  const refreshAll = () => {
    void refetch();
    bumpMutationKey();
  };

  const openSubjectRows = openSubject ? groups[openSubject] ?? [] : [];

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

  // Note: we don't bind `/` to focus this input because AppShell already
  // owns `/` as "jump to Ask." The search bar is reached via mouse or by
  // tabbing into it from the dropzone. If discoverability becomes a real
  // concern, a Cmd+K palette entry is the next step, not a keybind fight.

  const handleResultDelete = (doc: DocumentRowType) => {
    const name = doc.filename ?? "this source";
    // Search-results delete uses a native confirm so we don't need to haul the
    // full DeleteConfirmDialog state machine into this view. For nuanced
    // undo / rename / reassign, users drill into the subject.
    if (!window.confirm(`Delete "${name}"? This also removes its chunks and embeddings.`)) return;
    deleteDocument(doc.id)
      .then(refreshAll)
      .catch((err) => {
        console.error("Library search delete failed", err);
      });
  };

  return (
    <Stack className={styles.container} gap={6}>
      <header className={styles.header}>
        <div className={styles.headerCopy}>
          <Badge tone="info">Library</Badge>
          <Text as="h2" variant="display" weight="bold">
            Source-grounded documents, grouped the way you study.
          </Text>
          <Text tone="secondary">
            Import files, regroup subjects, and jump straight into the Reader scaffold from here.
          </Text>
        </div>
        <ImportDropzone onUploaded={refreshAll} />
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
      {data.value && data.value.length === 0 ? <LibraryEmptyState /> : null}

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
              <Stack gap={2}>
                <Text tone="secondary">
                  No documents match &ldquo;{trimmed}&rdquo;.
                </Text>
                <Text tone="tertiary" variant="caption">
                  Try a shorter phrase, a subject name, or clear the search to browse all subjects.
                </Text>
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
      {data.value && data.value.length > 0 && !isSearching ? (
        <SubjectCardGrid
          onSubjectOpen={(subject) => setOpenSubject(subject)}
          refreshKey={mutationKey}
        />
      ) : null}

      {openSubject && !isSearching ? (
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
            onSubjectRenamed={refreshAll}
            subject={openSubject}
          />
        </Stack>
      ) : null}

      {data.value && data.value.length > 0 && !openSubject && !isSearching ? (
        <Card padding="md">
          <Text tone="tertiary">
            {data.value.length} documents indexed across{" "}
            {Object.keys(groups).length} subjects.
          </Text>
        </Card>
      ) : null}
    </Stack>
  );
}
