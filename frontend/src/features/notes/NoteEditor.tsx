import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { createQuery } from "@/lib/query";
import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import { Ic } from "./components/NotesIcons";
import {
  notesOrganizationQuery,
  refreshNotesOrganization
} from "./state";
import styles from "./NoteEditor.module.css";

interface NoteEditorProps {
  /** The note id from the route. */
  id: string;
}

/**
 * Full-page writing surface for a single note.
 *
 * Layout: 720px centered content column (Word page width), title input
 * up top, contenteditable body underneath, a sticky toolbar with the
 * usual rich-text actions (bold, italic, underline, H1–H3, lists,
 * quote, code). A slim metadata strip carries the source pill and a
 * move-to-folder dropdown. Autosave on blur + ⌘S.
 *
 * Editor backend: native contenteditable + document.execCommand. Yes,
 * it's deprecated in spec; in practice it's what Apple Notes and Word
 * Online run on and behaves consistently across every WebKit /
 * Chromium today. The HTML the editor produces is saved verbatim and
 * re-rendered on load. When we want @-mentions / math / collab,
 * upgrade to TipTap or Lexical without touching the page shell.
 */
export function NoteEditor({ id }: NoteEditorProps) {
  // Fetch all notes once; find this one by id. A per-note GET endpoint
  // is a Phase B follow-up — for now the list fetch is fine (a single
  // user library tops out at a few hundred notes).
  const listQuery = useMemo(
    () => createQuery(() => notesApi.list({ limit: 500 })),
    []
  );
  useEffect(() => {
    const unsubscribe = listQuery.subscribe();
    void listQuery.refetch();
    return unsubscribe;
  }, [listQuery]);
  useEffect(() => {
    const unsubscribe = notesOrganizationQuery.subscribe();
    void notesOrganizationQuery.refetch();
    return unsubscribe;
  }, []);

  const allNotes = listQuery.data.value?.notes ?? [];
  const note = allNotes.find((n) => n.id === id) ?? null;
  const subjects = notesOrganizationQuery.data.value?.subjects ?? [];
  const loading = listQuery.loading.value ?? false;

  if (loading && note === null) {
    return (
      <div className={styles.page} data-stillwater="true">
        <div className={styles.skeleton} aria-hidden />
      </div>
    );
  }

  if (note === null) {
    return (
      <div className={styles.page} data-stillwater="true">
        <NotFoundState />
      </div>
    );
  }

  return (
    <EditorSurface key={note.id} note={note} subjects={subjects} />
  );
}

interface EditorSurfaceProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
}

function EditorSurface({ note, subjects }: EditorSurfaceProps) {
  const [title, setTitle] = useState(note.title || "Untitled note");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const bodyRef = useRef<HTMLDivElement | null>(null);
  const debounceRef = useRef<number | null>(null);
  const lastSavedRef = useRef({ title: note.title, content: note.content });

  // Mount body content once: contenteditable's innerHTML is the source
  // of truth from here on out. Setting it on every render would clobber
  // the user's caret position mid-type.
  useEffect(() => {
    if (!bodyRef.current) return;
    const isWorkspaceSeed = note.content === "\n";
    bodyRef.current.innerHTML = isWorkspaceSeed ? "" : note.content;
    // Focus the body. If empty (new workspace note), put the caret at
    // the start; otherwise leave selection alone so re-navigation
    // doesn't jump the user's last position.
    if (isWorkspaceSeed) {
      bodyRef.current.focus();
      const range = document.createRange();
      range.setStart(bodyRef.current, 0);
      range.collapse(true);
      const sel = window.getSelection();
      sel?.removeAllRanges();
      sel?.addRange(range);
    }
    lastSavedRef.current = { title: note.title, content: note.content };
    setTitle(note.title || "Untitled note");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note.id]);

  const flushSave = useCallback(async () => {
    if (!bodyRef.current) return;
    const nextTitle = title.trim() || "Untitled note";
    let nextContent = bodyRef.current.innerHTML;
    if (nextContent === "" || nextContent === "<br>") nextContent = "\n";
    if (
      nextTitle === lastSavedRef.current.title &&
      nextContent === lastSavedRef.current.content
    ) {
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await notesApi.save({
        title: nextTitle,
        content: nextContent,
        doc_id: note.doc_id ?? undefined,
        concept_id: note.concept_id ?? undefined,
        folder_id: note.folder_id,
        note_type: note.note_type
      });
      lastSavedRef.current = { title: nextTitle, content: nextContent };
      const stamp = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
      });
      setSavedAt(stamp);
      refreshNotesOrganization();
    } catch (err) {
      setSaveError((err as Error).message || "Save failed.");
    } finally {
      setSaving(false);
    }
  }, [note.doc_id, note.concept_id, note.folder_id, note.note_type, title]);

  // Debounced autosave during typing.
  const scheduleSave = useCallback(() => {
    if (debounceRef.current !== null) {
      window.clearTimeout(debounceRef.current);
    }
    debounceRef.current = window.setTimeout(() => {
      void flushSave();
    }, 1200);
  }, [flushSave]);

  // Clean up timer on unmount + final flush so leaving the page
  // doesn't drop a few hundred ms of typing.
  useEffect(() => {
    return () => {
      if (debounceRef.current !== null) {
        window.clearTimeout(debounceRef.current);
      }
      void flushSave();
    };
  }, [flushSave]);

  // ⌘S / Ctrl+S triggers an immediate save.
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        if (debounceRef.current !== null) {
          window.clearTimeout(debounceRef.current);
          debounceRef.current = null;
        }
        void flushSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [flushSave]);

  const applyCommand = (command: string, value?: string) => {
    // execCommand is the cross-browser-WebKit-tested path for
    // contenteditable formatting. focusing first ensures the command
    // applies to the editor, not the toolbar button.
    bodyRef.current?.focus();
    document.execCommand(command, false, value);
    scheduleSave();
  };

  const applyHeading = (level: 1 | 2 | 3 | 0) => {
    if (level === 0) {
      applyCommand("formatBlock", "<p>");
    } else {
      applyCommand("formatBlock", `<h${level}>`);
    }
  };

  const handleMove = async (event: Event) => {
    const value = (event.currentTarget as HTMLSelectElement).value;
    const next = value === "" ? null : value;
    if (next === (note.folder_id ?? null)) return;
    try {
      await notesApi.move(note.id, next);
      refreshNotesOrganization();
    } catch (err) {
      setSaveError((err as Error).message || "Move failed.");
    }
  };

  const sourceLabel = note.document_name ?? null;

  return (
    <div className={styles.page} data-stillwater="true">
      {/* Top bar: back, title input, saved indicator -------------- */}
      <header className={styles.topbar}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={() => navigateTo("/notes")}
          aria-label="Back to notes"
          title="Back to notes (Esc)"
        >
          <span aria-hidden>←</span>
          <span>Notes</span>
        </button>

        <div className={styles.savedIndicator}>
          {saveError ? (
            <span className={styles.savedErr} role="alert">{saveError}</span>
          ) : saving ? (
            <>
              <span className={[styles.savedDot, styles.savedDotPulse].join(" ")} aria-hidden />
              <span>Saving…</span>
            </>
          ) : (
            <>
              <span className={styles.savedDot} aria-hidden />
              <span>{savedAt ? `Saved · ${savedAt}` : "Synced"}</span>
            </>
          )}
        </div>
      </header>

      {/* Toolbar (sticky) ----------------------------------------- */}
      <Toolbar
        onCommand={applyCommand}
        onHeading={applyHeading}
      />

      {/* Page surface — Word-style centered column ---------------- */}
      <article className={styles.sheet}>
        <input
          className={styles.titleInput}
          value={title}
          onInput={(e) => {
            setTitle((e.currentTarget as HTMLInputElement).value);
            scheduleSave();
          }}
          onBlur={() => void flushSave()}
          placeholder="Untitled note"
          aria-label="Note title"
        />

        {/* Metadata strip — source pill + folder picker ---------- */}
        <div className={styles.meta}>
          {sourceLabel ? (
            <span className={styles.sourcePill}>
              <Ic.note className={styles.sourceIc} />
              <span>{sourceLabel}</span>
              {note.doc_id ? (
                <button
                  type="button"
                  className={styles.sourceJump}
                  onClick={() =>
                    note.doc_id &&
                    navigateTo(`/reader/${encodeURIComponent(note.doc_id)}`)
                  }
                >
                  Open ↗
                </button>
              ) : null}
            </span>
          ) : (
            <span className={[styles.sourcePill, styles.sourcePillMuted].join(" ")}>
              No source
            </span>
          )}

          <label className={styles.folderWrap}>
            <span className={styles.srOnly}>Move to folder</span>
            <select
              className={styles.folderSelect}
              value={note.folder_id ?? ""}
              onChange={handleMove}
            >
              <option value="">No folder</option>
              {subjects.map((subject) =>
                subject.folders.length > 0 ? (
                  <optgroup key={subject.name} label={subject.name}>
                    {subject.folders.map((folder) => (
                      <option key={folder.id} value={folder.id}>
                        {folder.name}
                      </option>
                    ))}
                  </optgroup>
                ) : null
              )}
            </select>
          </label>
        </div>

        {/* The writing canvas. ContentEditable + execCommand drives
            bold/italic/underline natively; the toolbar buttons fire
            the same commands so keyboard and click stay in sync. */}
        <div
          ref={bodyRef}
          className={styles.body}
          contentEditable
          spellcheck
          aria-label="Note body"
          onInput={scheduleSave}
          onBlur={() => void flushSave()}
        />
      </article>
    </div>
  );
}

interface ToolbarProps {
  onCommand: (command: string, value?: string) => void;
  onHeading: (level: 1 | 2 | 3 | 0) => void;
}

function Toolbar({ onCommand, onHeading }: ToolbarProps) {
  return (
    <nav aria-label="Formatting toolbar" className={styles.toolbar}>
      <ToolbarGroup>
        <ToolbarButton
          label="Bold"
          shortcut="⌘B"
          onClick={() => onCommand("bold")}
        >
          <span style={{ fontWeight: 700 }}>B</span>
        </ToolbarButton>
        <ToolbarButton
          label="Italic"
          shortcut="⌘I"
          onClick={() => onCommand("italic")}
        >
          <span style={{ fontStyle: "italic" }}>I</span>
        </ToolbarButton>
        <ToolbarButton
          label="Underline"
          shortcut="⌘U"
          onClick={() => onCommand("underline")}
        >
          <span style={{ textDecoration: "underline" }}>U</span>
        </ToolbarButton>
        <ToolbarButton
          label="Strikethrough"
          onClick={() => onCommand("strikeThrough")}
        >
          <span style={{ textDecoration: "line-through" }}>S</span>
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton label="Paragraph" onClick={() => onHeading(0)}>
          ¶
        </ToolbarButton>
        <ToolbarButton label="Heading 1" onClick={() => onHeading(1)}>
          H1
        </ToolbarButton>
        <ToolbarButton label="Heading 2" onClick={() => onHeading(2)}>
          H2
        </ToolbarButton>
        <ToolbarButton label="Heading 3" onClick={() => onHeading(3)}>
          H3
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Bulleted list"
          onClick={() => onCommand("insertUnorderedList")}
        >
          •
        </ToolbarButton>
        <ToolbarButton
          label="Numbered list"
          onClick={() => onCommand("insertOrderedList")}
        >
          1.
        </ToolbarButton>
        <ToolbarButton
          label="Indent"
          onClick={() => onCommand("indent")}
        >
          →|
        </ToolbarButton>
        <ToolbarButton
          label="Outdent"
          onClick={() => onCommand("outdent")}
        >
          |←
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Block quote"
          onClick={() => onCommand("formatBlock", "<blockquote>")}
        >
          ❝
        </ToolbarButton>
        <ToolbarButton
          label="Code block"
          onClick={() => onCommand("formatBlock", "<pre>")}
        >
          {"</>"}
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Undo"
          shortcut="⌘Z"
          onClick={() => onCommand("undo")}
        >
          ↶
        </ToolbarButton>
        <ToolbarButton
          label="Redo"
          shortcut="⌘⇧Z"
          onClick={() => onCommand("redo")}
        >
          ↷
        </ToolbarButton>
      </ToolbarGroup>
    </nav>
  );
}

function ToolbarGroup({ children }: { children: preact.ComponentChildren }) {
  return <span className={styles.toolbarGroup}>{children}</span>;
}

interface ToolbarButtonProps {
  label: string;
  shortcut?: string;
  onClick: () => void;
  children: preact.ComponentChildren;
}

function ToolbarButton({
  label,
  shortcut,
  onClick,
  children
}: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={styles.toolbarBtn}
      onMouseDown={(e) => {
        // Critical: prevent the button from stealing focus from the
        // editor. Without this, contenteditable loses its selection
        // when the user clicks the toolbar, and execCommand applies
        // to nothing.
        e.preventDefault();
      }}
      onClick={onClick}
      aria-label={shortcut ? `${label} (${shortcut})` : label}
      title={shortcut ? `${label} (${shortcut})` : label}
    >
      {children}
    </button>
  );
}

function NotFoundState() {
  return (
    <div className={styles.notFound}>
      <h1>Note not found.</h1>
      <p>
        That note might have been deleted, or the link is wrong. Head back to
        Notes and start again.
      </p>
      <button
        type="button"
        className={styles.notFoundBtn}
        onClick={() => navigateTo("/notes")}
      >
        ← Back to Notes
      </button>
    </div>
  );
}
