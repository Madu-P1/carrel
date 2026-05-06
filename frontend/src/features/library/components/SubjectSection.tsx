import { useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Badge, Button, Input, Stack, Text, toast } from "@/design-system";
import type { DocumentRow as DocumentRowType } from "@/services/api/endpoints";

import { useDeleteDocument } from "../hooks/useDeleteDocument";
import { useSetSubject } from "../hooks/useSetSubject";

import { DeleteConfirmDialog } from "./DeleteConfirmDialog";
import { DocumentRow } from "./DocumentRow";
import styles from "./SubjectSection.module.css";

interface SubjectSectionProps {
  documents: DocumentRowType[];
  onDocumentDeleted: () => void;
  /**
   * Fires after a successful rename. The new name is passed back so the
   * parent can update any state pinned to the old subject string (the
   * Library drill-in panel keys off `openSubject`; without this hand-off,
   * renaming an open subject leaves the panel pointing at a stale key).
   *
   * If the user "saves" with no actual change, `nextSubject ===
   * priorSubject` and the parent treats the call as a no-op.
   */
  onSubjectRenamed: (nextSubject: string) => void;
  subject: string;
}

export function SubjectSection({
  documents,
  onDocumentDeleted,
  onSubjectRenamed,
  subject
}: SubjectSectionProps) {
  const [collapsed, setCollapsed] = useState(false);
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(subject);
  const [deleteTarget, setDeleteTarget] = useState<DocumentRowType | null>(null);
  const { deleteDocument, loading: deleteLoading, error: deleteError } = useDeleteDocument();
  const { setSubject, loading: renameLoading, error: renameError } = useSetSubject();

  const handleRename = async () => {
    const nextSubject = draft.trim() || "General";
    const priorSubject = subject;
    try {
      await setSubject(
        documents.map((document) => document.id),
        nextSubject
      );
      setEditing(false);
      onSubjectRenamed(nextSubject);
      if (nextSubject !== priorSubject) {
        toast.success(`Subject renamed to "${nextSubject}"`, `${documents.length} document${documents.length === 1 ? "" : "s"} updated.`);
      }
    } catch (err) {
      toast.error("Rename failed", (err as Error).message);
    }
  };

  return (
    <section className={styles.section}>
      <header className={styles.header}>
        <div className={styles.titleWrap}>
          <Button
            aria-expanded={!collapsed}
            onClick={() => setCollapsed((value) => !value)}
            variant="ghost"
          >
            {collapsed ? "Expand" : "Collapse"}
          </Button>
          <Text as="h2" variant="h2" weight="semibold">
            {subject}
          </Text>
          <Badge tone="info">{documents.length} docs</Badge>
        </div>
        <div className={styles.headerActions}>
          {documents.length > 0 ? (
            <Button onClick={() => setEditing((value) => !value)} variant="secondary">
              {editing ? "Cancel" : "Rename subject"}
            </Button>
          ) : null}
        </div>
      </header>

      {!collapsed ? (
        <div className={styles.body}>
          <Stack gap={4}>
            {editing ? (
              <div className={styles.renameRow}>
                <Input
                  error={renameError.value?.message}
                  label="Subject name"
                  onInput={(event) => setDraft((event.currentTarget as HTMLInputElement).value)}
                  value={draft}
                />
                <Button isLoading={renameLoading.value} onClick={() => void handleRename()}>
                  Save
                </Button>
              </div>
            ) : null}

            <div className={styles.list}>
              {documents.length === 0 ? (
                <div className={styles.emptyFolder}>
                  <Text tone="secondary">No sources in this subject yet.</Text>
                </div>
              ) : (
                documents.map((document) => (
                  <DocumentRow
                    document={document}
                    key={document.id}
                    onDelete={() => setDeleteTarget(document)}
                    onOpen={() => navigateTo(`/reader/${document.id}`)}
                  />
                ))
              )}
            </div>
          </Stack>
        </div>
      ) : null}

      <DeleteConfirmDialog
        documentName={deleteTarget?.filename ?? "this source"}
        error={deleteError.value}
        loading={deleteLoading.value}
        onClose={() => setDeleteTarget(null)}
        onConfirm={async () => {
          if (!deleteTarget) {
            return;
          }
          await deleteDocument(deleteTarget.id);
          setDeleteTarget(null);
          onDocumentDeleted();
        }}
        open={deleteTarget !== null}
      />
    </section>
  );
}
