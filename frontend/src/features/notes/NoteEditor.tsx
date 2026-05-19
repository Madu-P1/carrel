import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState
} from "preact/hooks";

import { navigateTo } from "@/app/shell/useAppShell";
import { Markdown } from "@/design-system";
import { createQuery } from "@/lib/query";
import {
  notes as notesApi,
  type NoteOrganizationSubject,
  type NoteRecord
} from "@/services/api/endpoints";

import { Ic } from "./components/NotesIcons";
import { notesOrganizationQuery, refreshNotesOrganization } from "./state";
import { noteContentToMarkdown, serializeNoteMarkdown } from "./noteContent";
import type { StructuredEditorHandle } from "./StructuredMarkdownEditor";
import styles from "./NoteEditor.module.css";

type StructuredMarkdownEditorComponent =
  typeof import("./StructuredMarkdownEditor").StructuredMarkdownEditor;

interface NoteEditorProps {
  /** The note id from the route. */
  id: string;
}

/**
 * Full-page writing surface for a single note.
 *
 * Layout: 720px centered content column (Word page width), title input up
 * top, a structured writing surface underneath, a sticky toolbar with the
 * usual rich-text actions (bold, italic, H1-H3, lists, quote, code). A slim
 * metadata strip carries the source pill and a move-to-folder dropdown.
 *
 * Save semantics (2026-05-16 rewrite, after the duplicate-note bug):
 *   - NO autosave during typing. Typing only flips the dirty flag.
 *   - Save fires on: the visible "Save" button, ⌘S, or "Save & leave"
 *     when the user confirms the back-button prompt.
 *   - The save call passes `note_id: note.id`, so it UPDATEs the same
 *     row every time. The previous build called save() with note_id
 *     null, which made the server INSERT a fresh row per keystroke
 *     debounce — that's what produced the "Untitled / S / Sm / Smo /
 *     Smok" duplicate notes the user reported.
 *   - Delete: explicit button + window.confirm + DELETE /api/notes/:id,
 *     then navigate back to /notes.
 *
 * Editor backend: TipTap/ProseMirror document state with markdown persistence
 * and a safe JSX preview. Legacy HTML notes are converted once on load.
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

  return <EditorSurface key={note.id} note={note} subjects={subjects} />;
}

interface EditorSurfaceProps {
  note: NoteRecord;
  subjects: NoteOrganizationSubject[];
}

function EditorSurface({ note, subjects }: EditorSurfaceProps) {
  const [title, setTitle] = useState(note.title || "Untitled note");
  const [draftContent, setDraftContent] = useState(() =>
    noteContentToMarkdown(note.content)
  );
  const [mode, setMode] = useState<"write" | "preview">("write");
  const [savedAt, setSavedAt] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const editorHandleRef = useRef<StructuredEditorHandle | null>(null);
  const [editorReady, setEditorReady] = useState(false);
  const [StructuredEditorComponent, setStructuredEditorComponent] =
    useState<StructuredMarkdownEditorComponent | null>(null);
  const lastSavedRef = useRef({
    title: note.title,
    content: serializeNoteMarkdown(noteContentToMarkdown(note.content))
  });
  // Mirror of `dirty` for callbacks (keydown / navigation) that close
  // over an old render. Reading state inside a stable handler is the
  // canonical use case for a ref alongside state.
  const dirtyRef = useRef(false);

  // Mount body content once per note. Setting it on every render would
  // clobber the user's caret position mid-type.
  useEffect(() => {
    const nextDraft = noteContentToMarkdown(note.content);
    const savedContent = serializeNoteMarkdown(nextDraft);
    const isWorkspaceSeed = savedContent === "\n";
    setDraftContent(nextDraft);
    setMode("write");
    // Focus the body. If empty (new workspace note), put the caret at
    // the start; otherwise leave selection alone so re-navigation
    // doesn't jump the user's last position.
    if (isWorkspaceSeed) {
      window.requestAnimationFrame(() => {
        editorHandleRef.current?.focus();
      });
    }
    lastSavedRef.current = { title: note.title, content: savedContent };
    setTitle(note.title || "Untitled note");
    setDirty(false);
    dirtyRef.current = false;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [note.id]);

  const markDirty = useCallback(() => {
    if (!dirtyRef.current) {
      dirtyRef.current = true;
      setDirty(true);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    void import("./StructuredMarkdownEditor").then((module) => {
      if (!cancelled) {
        setStructuredEditorComponent(() => module.StructuredMarkdownEditor);
      }
    });
    return () => {
      cancelled = true;
    };
  }, []);

  const handleEditorReady = useCallback(
    (handle: StructuredEditorHandle | null) => {
      editorHandleRef.current = handle;
      setEditorReady(handle !== null);
    },
    []
  );

  const flushSave = useCallback(async (): Promise<boolean> => {
    const nextTitle = title.trim() || "Untitled note";
    const nextContent = serializeNoteMarkdown(
      editorHandleRef.current?.getMarkdown() ?? draftContent
    );
    if (
      nextTitle === lastSavedRef.current.title &&
      nextContent === lastSavedRef.current.content
    ) {
      // Nothing to save; clear dirty in case the user clicked Save on
      // an unchanged note.
      dirtyRef.current = false;
      setDirty(false);
      return true;
    }
    setSaving(true);
    setSaveError(null);
    try {
      await notesApi.save({
        // CRITICAL: this is the bug-fix anchor for the "every keystroke
        // creates a new note" regression. Threading note.id makes the
        // server UPSERT into the same row instead of INSERT-ing a new
        // one. See SaveNotePayload comment in endpoints.ts.
        note_id: note.id,
        title: nextTitle,
        content: nextContent,
        doc_id: note.doc_id ?? undefined,
        concept_id: note.concept_id ?? undefined,
        folder_id: note.folder_id,
        note_type: note.note_type
      });
      lastSavedRef.current = { title: nextTitle, content: nextContent };
      if (nextContent === "\n") setDraftContent("");
      dirtyRef.current = false;
      setDirty(false);
      const stamp = new Date().toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit"
      });
      setSavedAt(stamp);
      refreshNotesOrganization();
      return true;
    } catch (err) {
      setSaveError((err as Error).message || "Save failed.");
      return false;
    } finally {
      setSaving(false);
    }
  }, [
    note.id,
    note.doc_id,
    note.concept_id,
    note.folder_id,
    note.note_type,
    draftContent,
    title
  ]);

  // ⌘S / Ctrl+S triggers an explicit save. This is the ONLY automatic
  // path that fires `notesApi.save()` — no input debounce, no blur
  // handler, no unmount flush. The earlier autosave-everywhere design
  // is what created duplicate notes (see file-level comment).
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void flushSave();
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [flushSave]);

  // Browser-level "you have unsaved changes" guard. Fires when the user
  // closes the tab / reloads / navigates away via a real URL change.
  // The in-app back button has its own confirm path (see handleBack).
  useEffect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!dirtyRef.current) return;
      event.preventDefault();
      // Modern browsers ignore the message string but still show their
      // built-in "Leave site?" dialog when preventDefault is called and
      // returnValue is non-empty.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, []);

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

  const handleBack = useCallback(async () => {
    if (dirtyRef.current) {
      // window.confirm is the right primitive here. The user just clicked
      // a clearly-labeled Back button; we're not surprising them with a
      // modal mid-flow. OK = save then leave, Cancel = abandon changes.
      const proceed = window.confirm(
        "You have unsaved changes. Save before leaving?\n\nOK = Save and leave\nCancel = Discard changes and leave"
      );
      if (proceed) {
        const ok = await flushSave();
        if (!ok) {
          // Save failed; don't navigate away or the user loses work.
          return;
        }
      }
    }
    navigateTo("/notes");
  }, [flushSave]);

  const handleDelete = useCallback(async () => {
    const confirmed = window.confirm(
      `Delete this note?\n\n"${(note.title || "Untitled note").slice(0, 80)}"\n\nThis can't be undone.`
    );
    if (!confirmed) return;
    setDeleting(true);
    setSaveError(null);
    try {
      await notesApi.remove(note.id);
      refreshNotesOrganization();
      navigateTo("/notes");
    } catch (err) {
      setSaveError((err as Error).message || "Delete failed.");
      setDeleting(false);
    }
  }, [note.id, note.title]);

  const sourceLabel = note.document_name ?? null;

  return (
    <div className={styles.page} data-stillwater="true">
      {/* Top bar: back, status, Save / Delete --------------------- */}
      <header className={styles.topbar}>
        <button
          type="button"
          className={styles.backBtn}
          onClick={() => void handleBack()}
          aria-label="Back to notes"
          title="Back to notes"
        >
          <span aria-hidden>←</span>
          <span>Notes</span>
        </button>

        <div className={styles.topbarRight}>
          <div className={styles.savedIndicator}>
            {saveError ? (
              <span className={styles.savedErr} role="alert">
                {saveError}
              </span>
            ) : saving ? (
              <>
                <span
                  className={[styles.savedDot, styles.savedDotPulse].join(" ")}
                  aria-hidden
                />
                <span>Saving…</span>
              </>
            ) : dirty ? (
              <>
                <span
                  className={[styles.savedDot, styles.savedDotDirty].join(" ")}
                  aria-hidden
                />
                <span>Unsaved changes</span>
              </>
            ) : (
              <>
                <span className={styles.savedDot} aria-hidden />
                <span>{savedAt ? `Saved · ${savedAt}` : "Saved"}</span>
              </>
            )}
          </div>

          <div className={styles.topbarActions}>
            <button
              type="button"
              className={styles.deleteBtn}
              onClick={() => void handleDelete()}
              disabled={deleting || saving}
              aria-label="Delete note"
              title="Delete note"
            >
              {deleting ? "Deleting…" : "Delete"}
            </button>
            <button
              type="button"
              className={styles.saveBtn}
              onClick={() => void flushSave()}
              disabled={!dirty || saving}
              aria-label="Save note"
              title="Save (⌘S)"
            >
              {saving ? "Saving…" : "Save"}
            </button>
          </div>
        </div>
      </header>

      {/* Toolbar (sticky) ----------------------------------------- */}
      <Toolbar
        mode={mode}
        editorReady={editorReady}
        onModeChange={setMode}
        onBold={() => editorHandleRef.current?.toggleBold()}
        onItalic={() => editorHandleRef.current?.toggleItalic()}
        onStrike={() => editorHandleRef.current?.toggleStrike()}
        onHeading={(level) =>
          level === 0
            ? editorHandleRef.current?.setParagraph()
            : editorHandleRef.current?.toggleHeading(level)
        }
        onList={(ordered) =>
          ordered
            ? editorHandleRef.current?.toggleOrderedList()
            : editorHandleRef.current?.toggleBulletList()
        }
        onQuote={() => editorHandleRef.current?.toggleBlockquote()}
        onCodeBlock={() => editorHandleRef.current?.toggleCodeBlock()}
      />

      {/* Page surface — Word-style centered column ---------------- */}
      <article className={styles.sheet}>
        <input
          className={styles.titleInput}
          value={title}
          onInput={(e) => {
            setTitle((e.currentTarget as HTMLInputElement).value);
            markDirty();
          }}
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
            <span
              className={[styles.sourcePill, styles.sourcePillMuted].join(" ")}
            >
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

        {mode === "write" ? (
          StructuredEditorComponent ? (
            <StructuredEditorComponent
              key={note.id}
              initialMarkdown={draftContent}
              onChange={setDraftContent}
              onDirty={markDirty}
              onReady={handleEditorReady}
            />
          ) : (
            <p className={styles.editorLoading} role="status">
              Loading editor...
            </p>
          )
        ) : (
          <div
            className={styles.preview}
            tabIndex={0}
            aria-label="Note preview"
          >
            {draftContent.trim() ? (
              <Markdown
                source={draftContent}
                className={styles.previewMarkdown}
              />
            ) : (
              <p className={styles.previewEmpty}>Start writing...</p>
            )}
          </div>
        )}
      </article>
    </div>
  );
}

interface ToolbarProps {
  mode: "write" | "preview";
  editorReady: boolean;
  onModeChange: (mode: "write" | "preview") => void;
  onBold: () => void;
  onItalic: () => void;
  onStrike: () => void;
  onHeading: (level: 1 | 2 | 3 | 0) => void;
  onList: (ordered: boolean) => void;
  onQuote: () => void;
  onCodeBlock: () => void;
}

function Toolbar({
  mode,
  editorReady,
  onModeChange,
  onBold,
  onItalic,
  onStrike,
  onHeading,
  onList,
  onQuote,
  onCodeBlock
}: ToolbarProps) {
  const writeMode = mode === "write";
  const editing = writeMode && editorReady;
  return (
    <nav aria-label="Formatting toolbar" className={styles.toolbar}>
      <ToolbarGroup>
        <ToolbarButton
          label="Bold"
          shortcut="⌘B"
          disabled={!editing}
          onClick={onBold}
        >
          <span style={{ fontWeight: 700 }}>B</span>
        </ToolbarButton>
        <ToolbarButton
          label="Italic"
          shortcut="⌘I"
          disabled={!editing}
          onClick={onItalic}
        >
          <span style={{ fontStyle: "italic" }}>I</span>
        </ToolbarButton>
        <ToolbarButton
          label="Strikethrough"
          disabled={!editing}
          onClick={onStrike}
        >
          <span style={{ textDecoration: "line-through" }}>S</span>
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Paragraph"
          disabled={!editing}
          onClick={() => onHeading(0)}
        >
          ¶
        </ToolbarButton>
        <ToolbarButton
          label="Heading 1"
          disabled={!editing}
          onClick={() => onHeading(1)}
        >
          H1
        </ToolbarButton>
        <ToolbarButton
          label="Heading 2"
          disabled={!editing}
          onClick={() => onHeading(2)}
        >
          H2
        </ToolbarButton>
        <ToolbarButton
          label="Heading 3"
          disabled={!editing}
          onClick={() => onHeading(3)}
        >
          H3
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Bulleted list"
          disabled={!editing}
          onClick={() => onList(false)}
        >
          •
        </ToolbarButton>
        <ToolbarButton
          label="Numbered list"
          disabled={!editing}
          onClick={() => onList(true)}
        >
          1.
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSep} aria-hidden />

      <ToolbarGroup>
        <ToolbarButton
          label="Block quote"
          disabled={!editing}
          onClick={onQuote}
        >
          ❝
        </ToolbarButton>
        <ToolbarButton
          label="Code block"
          disabled={!editing}
          onClick={onCodeBlock}
        >
          {"</>"}
        </ToolbarButton>
      </ToolbarGroup>

      <span className={styles.toolbarSpacer} aria-hidden />

      <ToolbarGroup>
        <ModeButton active={writeMode} onClick={() => onModeChange("write")}>
          Write
        </ModeButton>
        <ModeButton active={!writeMode} onClick={() => onModeChange("preview")}>
          Preview
        </ModeButton>
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
  disabled?: boolean;
  onClick: () => void;
  children: preact.ComponentChildren;
}

function ToolbarButton({
  label,
  shortcut,
  disabled = false,
  onClick,
  children
}: ToolbarButtonProps) {
  return (
    <button
      type="button"
      className={styles.toolbarBtn}
      onMouseDown={(e) => {
        // Keep the editor selection stable while the toolbar click runs.
        e.preventDefault();
      }}
      onClick={onClick}
      disabled={disabled}
      aria-label={shortcut ? `${label} (${shortcut})` : label}
      title={shortcut ? `${label} (${shortcut})` : label}
    >
      {children}
    </button>
  );
}

function ModeButton({
  active,
  onClick,
  children
}: {
  active: boolean;
  onClick: () => void;
  children: preact.ComponentChildren;
}) {
  return (
    <button
      type="button"
      className={[styles.modeBtn, active ? styles.modeBtnActive : ""]
        .filter(Boolean)
        .join(" ")}
      onClick={onClick}
      aria-pressed={active}
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
