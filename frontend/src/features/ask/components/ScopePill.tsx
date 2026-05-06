import { useEffect, useMemo, useRef, useState } from "preact/hooks";

import { Icon } from "@/design-system";
import type { DocumentRow, SrsSubjectSummary } from "@/services/api/endpoints";

import styles from "./ScopePill.module.css";

export type AskScopeKind = "library" | "document" | "subject";

export interface AskScopeValue {
  kind: AskScopeKind;
  /** Populated when kind === "document". */
  docId?: string;
  docTitle?: string;
  /** Populated when kind === "subject". */
  subjectName?: string;
  /** Populated when any scope is indexing / not yet ready. v2 reads this
   *  from an ingestion readiness feed; v1 just reports "ready" assuming
   *  all documents the user can see in the picker have been ingested. */
  readiness?: "ready" | "indexing";
}

interface ScopePillProps {
  value: AskScopeValue;
  onChange: (next: AskScopeValue) => void;
  documents: DocumentRow[];
  subjects: SrsSubjectSummary[];
}

/**
 * Scope Pill.
 *
 * Above every Ask prompt, a persistent control that shows exactly what the
 * AI will see when it retrieves. The click opens a small popover with the
 * three v1 scopes — Library (no filter), Document (pick one), Subject
 * (pick a subject).
 *
 * Why this is the first trust fix: silent retrieval is magical until it
 * misses something, and then the user has no mental model of why. The
 * Scope Pill makes the corpus choice legible before the question is even
 * asked. Every answer surfaces which scope produced it.
 *
 * Design notes:
 *   - No modal. A popover that closes on outside-click / Esc.
 *   - Keyboard-first: the pill is a button; arrow keys cycle picker
 *     options; Enter commits.
 *   - Wide-mode friendly: when there are > 12 documents, the document
 *     list becomes searchable.
 *   - Respects DESIGN.md motion: the popover opens with fadeUp at
 *     --dur-fast; reduced-motion users get an instant swap.
 */
export function ScopePill({ value, onChange, documents, subjects }: ScopePillProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"root" | "pick-document" | "pick-subject">("root");
  const [docQuery, setDocQuery] = useState("");
  const rootRef = useRef<HTMLDivElement | null>(null);

  // Close on outside click / Esc. Focus-in doesn't count as outside —
  // moving focus to the picker search input is still "inside" the
  // popover subtree.
  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setOpen(false);
        setMode("root");
      }
    };
    const handleClickOutside = (e: MouseEvent) => {
      const root = rootRef.current;
      if (!root) return;
      const target = e.target as Node | null;
      if (target && root.contains(target)) return;
      setOpen(false);
      setMode("root");
    };
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("mousedown", handleClickOutside);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("mousedown", handleClickOutside);
    };
  }, [open]);

  const label = useMemo(() => labelFor(value), [value]);

  const filteredDocs = useMemo(() => {
    const q = docQuery.trim().toLowerCase();
    if (!q) return documents;
    return documents.filter((d) => (d.filename ?? "").toLowerCase().includes(q));
  }, [documents, docQuery]);

  const handlePickLibrary = () => {
    onChange({ kind: "library", readiness: "ready" });
    setOpen(false);
    setMode("root");
  };

  const handlePickDocument = (doc: DocumentRow) => {
    onChange({
      kind: "document",
      docId: doc.id,
      docTitle: doc.filename ?? "Untitled",
      readiness: "ready",
    });
    setOpen(false);
    setMode("root");
  };

  const handlePickSubject = (subject: SrsSubjectSummary) => {
    onChange({
      kind: "subject",
      subjectName: subject.subject_name,
      readiness: "ready",
    });
    setOpen(false);
    setMode("root");
  };

  return (
    <div className={styles.root} ref={rootRef}>
      <button
        aria-expanded={open}
        aria-haspopup="dialog"
        aria-label={`Scope: ${label}`}
        className={styles.pill}
        onClick={() => setOpen((v) => !v)}
        type="button"
      >
        <Icon name="library" size={14} />
        <span className={styles.pillLabel}>{label}</span>
        <Icon name="chevron-down" size={12} />
      </button>

      {open ? (
        <div className={styles.popover} role="dialog">
          {mode === "root" ? (
            <ul className={styles.list}>
              <li>
                <ScopeOption
                  active={value.kind === "library"}
                  description="All ingested sources. Default."
                  icon="library"
                  onClick={handlePickLibrary}
                  title="Library"
                />
              </li>
              <li>
                <ScopeOption
                  active={value.kind === "document"}
                  description={
                    value.kind === "document" && value.docTitle
                      ? `Current: ${value.docTitle}`
                      : `Pick one of ${documents.length} document${documents.length === 1 ? "" : "s"}`
                  }
                  icon="doc"
                  onClick={() => setMode("pick-document")}
                  title="Document"
                  trailing="→"
                  disabled={documents.length === 0}
                />
              </li>
              <li>
                <ScopeOption
                  active={value.kind === "subject"}
                  description={
                    value.kind === "subject" && value.subjectName
                      ? `Current: ${value.subjectName}`
                      : `Pick one of ${subjects.length} subject${subjects.length === 1 ? "" : "s"}`
                  }
                  icon="study"
                  onClick={() => setMode("pick-subject")}
                  title="Subject"
                  trailing="→"
                  disabled={subjects.length === 0}
                />
              </li>
            </ul>
          ) : mode === "pick-document" ? (
            <div className={styles.picker}>
              <input
                aria-label="Search documents"
                // Pop-over search field; auto-focus on open is the standard
                // pattern for keyboard-driven pickers (cmd-K, etc.).
                // eslint-disable-next-line jsx-a11y/no-autofocus
                autoFocus
                className={styles.search}
                onInput={(e) => setDocQuery((e.currentTarget as HTMLInputElement).value)}
                placeholder="Find a document…"
                type="search"
                value={docQuery}
              />
              <ul className={styles.pickerList}>
                {filteredDocs.length === 0 ? (
                  <li className={styles.pickerEmpty}>No documents match.</li>
                ) : (
                  filteredDocs.slice(0, 40).map((doc) => (
                    <li key={doc.id}>
                      <button
                        className={styles.pickerRow}
                        onClick={() => handlePickDocument(doc)}
                        type="button"
                      >
                        <span className={styles.pickerTitle}>{doc.filename ?? "Untitled"}</span>
                        {doc.subject_name ? (
                          <span className={styles.pickerMeta}>{doc.subject_name}</span>
                        ) : null}
                      </button>
                    </li>
                  ))
                )}
              </ul>
              <button
                className={styles.backRow}
                onClick={() => {
                  setMode("root");
                  setDocQuery("");
                }}
                type="button"
              >
                ← Back
              </button>
            </div>
          ) : (
            <div className={styles.picker}>
              <ul className={styles.pickerList}>
                {subjects.length === 0 ? (
                  <li className={styles.pickerEmpty}>No subjects yet.</li>
                ) : (
                  subjects.map((s) => (
                    <li key={s.subject_name}>
                      <button
                        className={styles.pickerRow}
                        onClick={() => handlePickSubject(s)}
                        type="button"
                      >
                        <span className={styles.pickerTitle}>{s.subject_name}</span>
                        <span className={styles.pickerMeta}>
                          {s.card_count} card{s.card_count === 1 ? "" : "s"}
                        </span>
                      </button>
                    </li>
                  ))
                )}
              </ul>
              <button
                className={styles.backRow}
                onClick={() => setMode("root")}
                type="button"
              >
                ← Back
              </button>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}

interface ScopeOptionProps {
  active: boolean;
  description: string;
  disabled?: boolean;
  icon: "library" | "doc" | "study";
  onClick: () => void;
  title: string;
  trailing?: string;
}

function ScopeOption({
  active,
  description,
  disabled = false,
  icon,
  onClick,
  title,
  trailing,
}: ScopeOptionProps) {
  return (
    <button
      aria-pressed={active}
      className={[styles.option, active ? styles.optionActive : ""].filter(Boolean).join(" ")}
      disabled={disabled}
      onClick={onClick}
      type="button"
    >
      <span className={styles.optionIcon} aria-hidden>
        <Icon name={icon} size={14} />
      </span>
      <span className={styles.optionBody}>
        <span className={styles.optionTitle}>{title}</span>
        <span className={styles.optionDescription}>{description}</span>
      </span>
      {trailing ? <span className={styles.optionTrailing} aria-hidden>{trailing}</span> : null}
    </button>
  );
}

function labelFor(value: AskScopeValue): string {
  if (value.kind === "document") return `Doc: ${value.docTitle ?? "…"}`;
  if (value.kind === "subject") return `Subject: ${value.subjectName ?? "…"}`;
  return "Library";
}
