import { useState } from "preact/hooks";

import { Badge, Button, Card, Icon, Stack, Text } from "@/design-system";

import { groupBySubject } from "./utils/group-by-subject";
import { useDocumentsQuery } from "./hooks/useDocumentsQuery";
import { DuplicateCleanupPanel } from "./components/DuplicateCleanupPanel";
import { ImportDropzone } from "./components/ImportDropzone";
import { LibraryEmptyState } from "./components/LibraryEmptyState";
import { LibraryErrorState } from "./components/LibraryErrorState";
import { SubjectCardGrid } from "./components/SubjectCardGrid";
import { SubjectSection } from "./components/SubjectSection";
import styles from "./LibraryView.module.css";

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
  const documents = data.value ?? [];
  const groups = groupBySubject(documents);

  const bumpMutationKey = () => setMutationKey((k) => k + 1);
  const refreshAll = () => {
    void refetch();
    bumpMutationKey();
  };

  const openSubjectRows = openSubject ? groups[openSubject] ?? [] : [];

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

      {loading.value && !data.value ? <LibrarySkeleton /> : null}
      {error.value ? <LibraryErrorState error={error.value} onRetry={() => void refetch()} /> : null}
      {data.value && data.value.length === 0 ? <LibraryEmptyState /> : null}

      {data.value && data.value.length > 0 ? (
        <DuplicateCleanupPanel onCleanupComplete={refreshAll} />
      ) : null}

      {/*
        Subject dashboard — the Library home. When the user clicks into a
        subject, we render that subject's file list below with a breadcrumb
        back. The grid itself stays visible so comparing subjects is one
        click away.
      */}
      {data.value && data.value.length > 0 ? (
        <SubjectCardGrid
          onSubjectOpen={(subject) => setOpenSubject(subject)}
          refreshKey={mutationKey}
        />
      ) : null}

      {openSubject ? (
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

      {data.value && data.value.length > 0 && !openSubject ? (
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
