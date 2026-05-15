import { useState } from "preact/hooks";

import { Icon, Text } from "@/design-system";
import {
  notes as notesApi,
  type NoteOrganizationSubject
} from "@/services/api/endpoints";

import styles from "./SubjectRail.module.css";

export type RailSelection =
  | { kind: "all" }
  | { kind: "subject"; subject: string }
  | { kind: "folder"; folder: string; subject: string; name: string }
  | { kind: "unsorted"; subject: string }
  | { kind: "orphan" };

interface SubjectRailProps {
  subjects: NoteOrganizationSubject[];
  selection: RailSelection;
  loading: boolean;
  onSelect: (next: RailSelection) => void;
  /** Called after any folder mutation so the parent can refetch the
   *  organization payload and the notes list together. */
  onChanged: () => void;
}

/**
 * The left rail of the global Notes page.
 *
 * Renders an "All notes" entry, then a section per subject. Each
 * subject section can be expanded to show its folders + an inline
 * "+ New folder" affordance + an "Unsorted" entry (notes whose
 * resolved subject is this one but aren't assigned to any folder).
 *
 * Rename and delete on folders are accessible via small icon
 * buttons that appear on hover (and via the keyboard always — they're
 * focusable, not display:none).
 */
export function SubjectRail({
  subjects,
  selection,
  loading,
  onSelect,
  onChanged
}: SubjectRailProps) {
  // Expanded state is local: collapsing/expanding a subject group is a
  // pure UI concern and doesn't need to persist or round-trip. We
  // default every subject to expanded so the rail's organization is
  // visible without an extra click.
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});
  const totalNotes = subjects.reduce((sum, s) => sum + s.note_count, 0);

  return (
    <aside aria-label="Notes navigation" className={styles.rail}>
      <button
        type="button"
        className={[
          styles.allRow,
          selection.kind === "all" ? styles.allRowActive : ""
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => onSelect({ kind: "all" })}
        aria-current={selection.kind === "all" ? "page" : undefined}
      >
        <span className={styles.allLabel}>All notes</span>
        <span className={styles.count}>{totalNotes}</span>
      </button>

      {loading && subjects.length === 0 ? (
        <div className={styles.skeleton} aria-hidden>
          <div className={styles.skeletonRow} />
          <div className={styles.skeletonRow} />
        </div>
      ) : null}

      {subjects.map((subject) => {
        const isCollapsed = collapsed[subject.name] ?? false;
        const subjectActive =
          (selection.kind === "subject" && selection.subject === subject.name) ||
          (selection.kind === "unsorted" && selection.subject === subject.name) ||
          (selection.kind === "folder" && selection.subject === subject.name);
        const folderedTotal = subject.folders.reduce(
          (sum, folder) => sum + folder.note_count,
          0
        );
        const unsortedCount = Math.max(0, subject.note_count - folderedTotal);

        return (
          <section className={styles.subjectGroup} key={subject.name}>
            <div className={styles.subjectHeader}>
              <button
                type="button"
                aria-expanded={!isCollapsed}
                aria-label={`Toggle ${subject.name} folders`}
                className={styles.disclosure}
                onClick={() =>
                  setCollapsed((prev) => ({
                    ...prev,
                    [subject.name]: !isCollapsed
                  }))
                }
              >
                {/*
                 * Icon primitive doesn't accept className, so we apply
                 * the rotation to a wrapping span. The span is
                 * inline-flex so it doesn't add extra layout slack
                 * around the 12×12 glyph.
                 */}
                <span
                  className={isCollapsed ? "" : styles.disclosureOpen}
                  style={{ display: "inline-flex" }}
                >
                  <Icon name="chevron-right" size={12} />
                </span>
              </button>
              <button
                type="button"
                className={[
                  styles.subjectRow,
                  subjectActive && selection.kind === "subject"
                    ? styles.subjectRowActive
                    : ""
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() =>
                  onSelect(
                    subject.name === "Unfiled"
                      ? { kind: "orphan" }
                      : { kind: "subject", subject: subject.name }
                  )
                }
                aria-current={
                  subjectActive && selection.kind === "subject" ? "page" : undefined
                }
              >
                <span className={styles.subjectName}>{subject.name}</span>
                <span className={styles.count}>{subject.note_count}</span>
              </button>
            </div>

            {!isCollapsed && subject.name !== "Unfiled" ? (
              <ul className={styles.folderList}>
                {subject.folders.map((folder) => (
                  <FolderRow
                    key={folder.id}
                    folder={folder}
                    subjectName={subject.name}
                    active={
                      selection.kind === "folder" && selection.folder === folder.id
                    }
                    onSelect={() =>
                      onSelect({
                        kind: "folder",
                        folder: folder.id,
                        subject: subject.name,
                        name: folder.name
                      })
                    }
                    onChanged={onChanged}
                  />
                ))}
                {unsortedCount > 0 ? (
                  <li>
                    <button
                      type="button"
                      className={[
                        styles.folderRow,
                        selection.kind === "unsorted" &&
                        selection.subject === subject.name
                          ? styles.folderRowActive
                          : ""
                      ]
                        .filter(Boolean)
                        .join(" ")}
                      onClick={() =>
                        onSelect({ kind: "unsorted", subject: subject.name })
                      }
                    >
                      <span className={styles.folderLabel}>
                        <em>Unsorted</em>
                      </span>
                      <span className={styles.count}>{unsortedCount}</span>
                    </button>
                  </li>
                ) : null}
                <li>
                  <NewFolderRow
                    subjectName={subject.name}
                    onChanged={onChanged}
                  />
                </li>
              </ul>
            ) : null}
          </section>
        );
      })}

      {!loading && subjects.length === 0 ? (
        <Text tone="tertiary" variant="caption">
          No notes yet. Save a note from the Reader and it will appear
          here, grouped by its source's subject.
        </Text>
      ) : null}
    </aside>
  );
}

interface FolderRowProps {
  folder: { id: string; name: string; note_count: number };
  subjectName: string;
  active: boolean;
  onSelect: () => void;
  onChanged: () => void;
}

function FolderRow({
  folder,
  subjectName,
  active,
  onSelect,
  onChanged
}: FolderRowProps) {
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(folder.name);
  const [error, setError] = useState<string | null>(null);

  const commitRename = async () => {
    const clean = name.trim();
    if (!clean || clean === folder.name) {
      setRenaming(false);
      setName(folder.name);
      return;
    }
    setError(null);
    try {
      await notesApi.folders.update(folder.id, { name: clean });
      setRenaming(false);
      onChanged();
    } catch (err) {
      setError((err as Error).message || "Could not rename the folder.");
    }
  };

  const handleDelete = async () => {
    // Confirmation lives in window.confirm for v1 — a dedicated
    // confirm dialog is on the polish list but a Mac-native confirm
    // is good enough to keep us from cutting a Dialog for one button.
    if (
      typeof window !== "undefined" &&
      !window.confirm(
        `Delete the folder "${folder.name}"? Notes inside will move back to ${subjectName} unsorted.`
      )
    ) {
      return;
    }
    try {
      await notesApi.folders.remove(folder.id);
      onChanged();
    } catch (err) {
      setError((err as Error).message || "Could not delete the folder.");
    }
  };

  return (
    <li>
      <div
        className={[
          styles.folderRow,
          active ? styles.folderRowActive : ""
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {renaming ? (
          <input
            aria-label="Folder name"
            className={styles.renameInput}
            value={name}
            onInput={(e) => setName((e.currentTarget as HTMLInputElement).value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                void commitRename();
              }
              if (e.key === "Escape") {
                e.preventDefault();
                setRenaming(false);
                setName(folder.name);
              }
            }}
            onBlur={() => void commitRename()}
            autoFocus
          />
        ) : (
          <button
            type="button"
            className={styles.folderLabelBtn}
            onClick={onSelect}
            aria-current={active ? "page" : undefined}
          >
            <span className={styles.folderLabel}>{folder.name}</span>
            <span className={styles.count}>{folder.note_count}</span>
          </button>
        )}
        <div className={styles.folderActions}>
          <button
            type="button"
            aria-label={`Rename folder ${folder.name}`}
            className={styles.folderIconBtn}
            onClick={() => setRenaming(true)}
          >
            <Icon name="edit" size={12} />
          </button>
          <button
            type="button"
            aria-label={`Delete folder ${folder.name}`}
            className={styles.folderIconBtn}
            onClick={() => void handleDelete()}
          >
            <Icon name="trash" size={12} />
          </button>
        </div>
      </div>
      {error ? (
        <p className={styles.folderError} role="alert">
          {error}
        </p>
      ) : null}
    </li>
  );
}

function NewFolderRow({
  subjectName,
  onChanged
}: {
  subjectName: string;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const commit = async () => {
    const clean = name.trim();
    if (!clean) {
      setEditing(false);
      setName("");
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await notesApi.folders.create({ name: clean, subject_name: subjectName });
      setName("");
      setEditing(false);
      onChanged();
    } catch (err) {
      setError((err as Error).message || "Could not create the folder.");
    } finally {
      setSaving(false);
    }
  };

  if (!editing) {
    return (
      <button
        type="button"
        className={styles.newFolderTrigger}
        onClick={() => setEditing(true)}
      >
        <Icon name="plus" size={12} />
        <span>New folder</span>
      </button>
    );
  }

  return (
    <div className={styles.newFolderRow}>
      <input
        aria-label={`New folder name for ${subjectName}`}
        className={styles.renameInput}
        value={name}
        placeholder="Folder name"
        onInput={(e) => setName((e.currentTarget as HTMLInputElement).value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            void commit();
          }
          if (e.key === "Escape") {
            e.preventDefault();
            setEditing(false);
            setName("");
          }
        }}
        onBlur={() => void commit()}
        disabled={saving}
        autoFocus
      />
      {error ? (
        <p className={styles.folderError} role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
