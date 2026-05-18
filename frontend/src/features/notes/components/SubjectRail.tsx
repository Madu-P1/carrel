import { useEffect, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import {
  notes as notesApi,
  type NoteOrganizationSubject
} from "@/services/api/endpoints";

import {
  notesOrganizationQuery,
  notesSelection,
  refreshNotesOrganization,
  setNotesSelection,
  type RailSelection
} from "../state";
import { Ic } from "./NotesIcons";
import styles from "./SubjectRail.module.css";

/**
 * Notes-rail content body (no wrapper aside, no brand mark).
 *
 * Renders inside the AppShell's WorkspaceSidebar slot when the user is
 * on /notes — the AppShell provides the brand mark above and the
 * TodayPanel + ProviderFooter below. This component owns only the
 * middle: Workspace virtual filters + Subjects + folder CRUD.
 *
 * State is read from the module-level notes signals so the same
 * selection is shared with NotesPage's main pane.
 */
export function SubjectRail() {
  const subjects = notesOrganizationQuery.data.value?.subjects ?? [];
  const loading = notesOrganizationQuery.loading.value ?? false;
  const selection = notesSelection.value;

  // Subscribe + fetch once when this component mounts (the rail lives
  // in the AppShell so it only mounts when /notes is the active route).
  useEffect(() => {
    const unsubscribe = notesOrganizationQuery.subscribe();
    void notesOrganizationQuery.refetch();
    return unsubscribe;
  }, []);

  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({});

  const totalNotes = subjects.reduce((sum, s) => sum + s.note_count, 0);
  const inboxCount = subjects.reduce(
    (sum, s) =>
      sum + (s.note_count - s.folders.reduce((a, f) => a + f.note_count, 0)),
    0
  );

  const railSubjects = subjects.filter(
    (s) => s.note_count > 0 || s.folders.length > 0
  );

  const onChanged = refreshNotesOrganization;

  return (
    <div className={styles.rail}>
      {/* WORKSPACE section ─────────────────────────────────────── */}
      <nav className={styles.section}>
        <div className={styles.label}>Workspace</div>
        <ul className={styles.list}>
          <RailItem
            icon={<Ic.note className={styles.itemIc} />}
            label="All notes"
            count={totalNotes > 0 ? totalNotes : null}
            active={selection.kind === "all"}
            onSelect={() => setNotesSelection({ kind: "all" })}
          />
          <RailItem
            icon={
              <Ic.star
                className={[
                  styles.itemIc,
                  inboxCount > 0 ? styles.itemIcStar : ""
                ]
                  .filter(Boolean)
                  .join(" ")}
              />
            }
            label="Unsorted"
            count={inboxCount > 0 ? inboxCount : null}
            countAccent
            active={selection.kind === "inbox"}
            onSelect={() => setNotesSelection({ kind: "inbox" })}
          />
          <RailItem
            icon={<Ic.clock className={styles.itemIc} />}
            label="This week"
            count={null}
            active={selection.kind === "this-week"}
            onSelect={() => setNotesSelection({ kind: "this-week" })}
          />
        </ul>
      </nav>

      {/* SUBJECTS section ──────────────────────────────────────── */}
      <nav className={styles.section}>
        <div className={[styles.label, styles.labelRow].join(" ")}>
          <span>Subjects</span>
        </div>

        {loading && railSubjects.length === 0 ? (
          <div className={styles.skeleton} aria-hidden>
            <div className={styles.skeletonRow} />
            <div className={styles.skeletonRow} />
          </div>
        ) : null}

        <ul className={styles.list}>
          {railSubjects.map((subject) => (
            <SubjectGroup
              key={subject.name}
              subject={subject}
              selection={selection}
              collapsed={collapsed[subject.name] ?? false}
              onToggleCollapsed={() =>
                setCollapsed((prev) => ({
                  ...prev,
                  [subject.name]: !(prev[subject.name] ?? false)
                }))
              }
              onChanged={onChanged}
            />
          ))}
        </ul>

        {!loading && railSubjects.length === 0 ? (
          <div className={styles.empty}>
            <p className={styles.emptyHead}>No subjects yet.</p>
            <p>
              Subjects appear here once you save a note tied to a document.
              They group by the document's subject — Cardiology, Tort law,
              and so on.
            </p>
            <button
              type="button"
              className={styles.emptyAction}
              onClick={() => navigateTo("/library")}
            >
              Go to Library →
            </button>
          </div>
        ) : null}
      </nav>
    </div>
  );
}

interface RailItemProps {
  icon: preact.JSX.Element;
  label: string;
  count: number | null;
  countAccent?: boolean;
  active: boolean;
  onSelect: () => void;
}

function RailItem({
  icon,
  label,
  count,
  countAccent = false,
  active,
  onSelect
}: RailItemProps) {
  return (
    <li>
      <button
        type="button"
        className={[styles.item, active ? styles.itemActive : ""]
          .filter(Boolean)
          .join(" ")}
        onClick={onSelect}
        aria-current={active ? "page" : undefined}
      >
        {icon}
        <span>{label}</span>
        {count !== null ? (
          <span
            className={[styles.count, countAccent ? styles.countAccent : ""]
              .filter(Boolean)
              .join(" ")}
          >
            {count}
          </span>
        ) : null}
      </button>
    </li>
  );
}

interface SubjectGroupProps {
  subject: NoteOrganizationSubject;
  selection: RailSelection;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onChanged: () => void;
}

function SubjectGroup({
  subject,
  selection,
  collapsed,
  onToggleCollapsed,
  onChanged
}: SubjectGroupProps) {
  const subjectActive =
    (selection.kind === "subject" && selection.subject === subject.name) ||
    (selection.kind === "folder" && selection.subject === subject.name);
  const folderedTotal = subject.folders.reduce(
    (sum, f) => sum + f.note_count,
    0
  );
  const unsortedCount = Math.max(0, subject.note_count - folderedTotal);

  return (
    <li className={styles.subj}>
      <button
        type="button"
        className={[
          styles.subjHead,
          subjectActive && selection.kind === "subject"
            ? styles.subjHeadActive
            : ""
        ]
          .filter(Boolean)
          .join(" ")}
        onClick={() => {
          if (subject.name === "Unfiled") {
            setNotesSelection({ kind: "orphan" });
          } else {
            setNotesSelection({ kind: "subject", subject: subject.name });
          }
        }}
        aria-current={
          subjectActive && selection.kind === "subject" ? "page" : undefined
        }
      >
        <span
          className={styles.chevWrap}
          onClick={(e) => {
            e.stopPropagation();
            onToggleCollapsed();
          }}
          role="button"
          tabIndex={-1}
          aria-label={`Toggle ${subject.name} folders`}
        >
          {collapsed ? (
            <Ic.chevronR className={styles.chev} />
          ) : (
            <Ic.chevron className={styles.chev} />
          )}
        </span>
        <span className={styles.subjName}>{subject.name}</span>
        <span className={styles.count}>{subject.note_count}</span>
      </button>

      {!collapsed && subject.name !== "Unfiled" ? (
        <ul className={styles.folders}>
          {subject.folders.map((folder) => (
            <FolderRow
              key={folder.id}
              folder={folder}
              subjectName={subject.name}
              active={
                selection.kind === "folder" && selection.folder === folder.id
              }
              onSelect={() =>
                setNotesSelection({
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
                  styles.folder,
                  selection.kind === "unsorted" &&
                  selection.subject === subject.name
                    ? styles.folderActive
                    : ""
                ]
                  .filter(Boolean)
                  .join(" ")}
                onClick={() =>
                  setNotesSelection({ kind: "unsorted", subject: subject.name })
                }
              >
                <Ic.folder className={styles.folderIc} />
                <span>
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
    </li>
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
        className={[styles.folderRow, active ? styles.folderActive : ""]
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
            className={styles.folder}
            onClick={onSelect}
            onDblClick={() => setRenaming(true)}
            aria-current={active ? "page" : undefined}
          >
            <Ic.folder className={styles.folderIc} />
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
            <Ic.edit />
          </button>
          <button
            type="button"
            aria-label={`Delete folder ${folder.name}`}
            className={styles.folderIconBtn}
            onClick={() => void handleDelete()}
          >
            <Ic.trash />
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
        className={[styles.folder, styles.folderNew].join(" ")}
        onClick={() => setEditing(true)}
      >
        <Ic.plus className={styles.folderIc} />
        <span>New folder</span>
      </button>
    );
  }

  return (
    <div className={styles.newFolderEditor}>
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
