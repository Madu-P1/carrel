import { useEffect, useRef, useState } from "preact/hooks";

import {
  markdownToStructuredDoc,
  structuredDocToMarkdown
} from "./structuredNoteDocument";
import { safeNoteHref } from "./safeNoteHref";
import styles from "./NoteEditor.module.css";

type TipTapEditor = import("@tiptap/core").Editor;

export interface StructuredEditorHandle {
  focus: () => void;
  getMarkdown: () => string;
  setParagraph: () => void;
  toggleBold: () => void;
  toggleItalic: () => void;
  toggleStrike: () => void;
  toggleHeading: (level: 1 | 2 | 3) => void;
  toggleBulletList: () => void;
  toggleOrderedList: () => void;
  toggleBlockquote: () => void;
  toggleCodeBlock: () => void;
}

interface StructuredMarkdownEditorProps {
  initialMarkdown: string;
  onChange: (markdown: string) => void;
  onDirty: () => void;
  onReady: (handle: StructuredEditorHandle | null) => void;
}

export function StructuredMarkdownEditor({
  initialMarkdown,
  onChange,
  onDirty,
  onReady
}: StructuredMarkdownEditorProps) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const editorRef = useRef<TipTapEditor | null>(null);
  const initialMarkdownRef = useRef(initialMarkdown);
  const onChangeRef = useRef(onChange);
  const onDirtyRef = useRef(onDirty);
  const onReadyRef = useRef(onReady);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    onChangeRef.current = onChange;
    onDirtyRef.current = onDirty;
    onReadyRef.current = onReady;
  }, [onChange, onDirty, onReady]);

  useEffect(() => {
    let cancelled = false;

    const loadEditor = async () => {
      const [{ Editor }, { default: StarterKit }, { default: Placeholder }] =
        await Promise.all([
          import("@tiptap/core"),
          import("@tiptap/starter-kit"),
          import("@tiptap/extension-placeholder")
        ]);

      if (cancelled || !hostRef.current) return;

      const editor = new Editor({
        element: hostRef.current,
        extensions: [
          StarterKit.configure({
            link: {
              autolink: false,
              linkOnPaste: false,
              openOnClick: false,
              HTMLAttributes: {
                rel: "noopener noreferrer",
                target: "_blank"
              },
              isAllowedUri: (url: string) => safeNoteHref(url) !== null
            }
          }),
          Placeholder.configure({
            placeholder: "Start writing..."
          })
        ],
        content: markdownToStructuredDoc(initialMarkdownRef.current),
        editorProps: {
          attributes: {
            "aria-label": "Note body",
            "aria-multiline": "true",
            class: styles.structuredProse,
            role: "textbox",
            spellcheck: "true"
          }
        },
        injectCSS: false,
        onUpdate: ({ editor: updatedEditor }) => {
          onChangeRef.current(structuredDocToMarkdown(updatedEditor.getJSON()));
          onDirtyRef.current();
        }
      });

      editorRef.current = editor;
      onReadyRef.current(createHandle(editor));
      if (!cancelled) setLoading(false);
    };

    void loadEditor();

    return () => {
      cancelled = true;
      onReadyRef.current(null);
      editorRef.current?.destroy();
      editorRef.current = null;
    };
  }, []);

  return (
    <div className={styles.structuredEditor}>
      {loading ? (
        <p className={styles.editorLoading} role="status" aria-live="polite">
          Loading editor...
        </p>
      ) : null}
      <div ref={hostRef} />
    </div>
  );
}

function createHandle(editor: TipTapEditor): StructuredEditorHandle {
  const chain = () => editor.chain().focus();
  return {
    focus: () => {
      editor.commands.focus();
    },
    getMarkdown: () => structuredDocToMarkdown(editor.getJSON()),
    setParagraph: () => {
      chain().setParagraph().run();
    },
    toggleBold: () => {
      chain().toggleBold().run();
    },
    toggleItalic: () => {
      chain().toggleItalic().run();
    },
    toggleStrike: () => {
      chain().toggleStrike().run();
    },
    toggleHeading: (level) => {
      chain().toggleHeading({ level }).run();
    },
    toggleBulletList: () => {
      chain().toggleBulletList().run();
    },
    toggleOrderedList: () => {
      chain().toggleOrderedList().run();
    },
    toggleBlockquote: () => {
      chain().toggleBlockquote().run();
    },
    toggleCodeBlock: () => {
      chain().toggleCodeBlock().run();
    }
  };
}
