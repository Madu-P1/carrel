import { useEffect, useState } from "preact/hooks";

import {
  DEFAULT_PROJECT,
  clearSource,
  knownProjects,
  loadedSource,
  refreshSources,
  setDocumentProject,
  sourceDocs,
  sourceUpload,
  setActiveRecord,
  sourcesError,
  uploadSource,
  type SourceDoc
} from "./source";
import styles from "./cachet.module.css";

/**
 * Sources: the library of records Cachet checks drafts against. Add a record
 * (executed contract, brief, exhibit), file it into a project, and see everything
 * you have added in one place. Pick which record the next verification grounds
 * against; refuse what cannot be traced to it. On-device: nothing leaves the machine.
 */

const NEW_PROJECT = "__new__";

function groupByProject(docs: SourceDoc[]): { project: string; items: SourceDoc[] }[] {
  const map = new Map<string, SourceDoc[]>();
  for (const d of docs) {
    const key = d.project || DEFAULT_PROJECT;
    const bucket = map.get(key);
    if (bucket) bucket.push(d);
    else map.set(key, [d]);
  }
  return [...map.entries()]
    .map(([project, items]) => ({ project, items }))
    .sort((a, b) => a.project.localeCompare(b.project));
}

function metaLine(doc: SourceDoc): string {
  const bits: string[] = [];
  if (doc.fileType) bits.push(doc.fileType.toUpperCase());
  if (typeof doc.pageCount === "number" && doc.pageCount > 0) {
    bits.push(`${doc.pageCount} ${doc.pageCount === 1 ? "page" : "pages"}`);
  }
  return bits.join(" · ");
}

export function SourcesView() {
  const [error, setError] = useState<string | null>(null);
  const [project, setProject] = useState<string>(DEFAULT_PROJECT);
  const [newProject, setNewProject] = useState<string>("");

  const docs = sourceDocs.value;
  const upload = sourceUpload.value;
  const active = loadedSource.value;
  const loadError = sourcesError.value;

  useEffect(() => {
    // Token-safe visual fixture (same idiom as the verify view's ?demo): render the
    // library with sample records without a backend, so the layout can be reviewed
    // at real widths. Only fires for the exact query flag; never in normal use.
    const params = new URLSearchParams(globalThis.location?.search ?? "");
    if (params.get("fixture") === "sources") {
      sourceDocs.value = [
        {
          id: "d-msa",
          filename: "Apex–Northwind MSA (executed).pdf",
          project: "Apex v. Northwind",
          pageCount: 14,
          fileType: "pdf"
        },
        {
          id: "d-ex",
          filename: "Exhibit B – Pricing Schedule.docx",
          project: "Apex v. Northwind",
          pageCount: 3,
          fileType: "docx"
        },
        { id: "d-nda", filename: "Mutual NDA.pdf", project: "Sources", pageCount: 6, fileType: "pdf" }
      ];
      loadedSource.value = { docId: "d-msa", filename: "Apex–Northwind MSA (executed).pdf" };
      return;
    }
    void refreshSources();
  }, []);

  const projectChoices = knownProjects();
  const targetProject = (project === NEW_PROJECT ? newProject : project).trim() || DEFAULT_PROJECT;

  async function onFiles(files: FileList | null | undefined) {
    const file = files && files[0];
    if (!file || upload) return;
    setError(null);
    try {
      await uploadSource(file, targetProject);
      // Settle the picker onto the project we just filed into.
      if (project === NEW_PROJECT) {
        setProject(targetProject);
        setNewProject("");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "The document could not be loaded.");
    }
  }

  async function onMove(doc: SourceDoc, nextProject: string) {
    if (!nextProject || nextProject === doc.project) return;
    setError(null);
    try {
      await setDocumentProject(doc.id, nextProject);
    } catch (e) {
      setError(e instanceof Error ? e.message : "The record could not be moved.");
    }
  }

  const groups = docs && docs.length > 0 ? groupByProject(docs) : [];

  return (
    <section className={`${styles.plainView} ${styles.sourcesView}`}>
      <div className={styles.plainHead}>
        <h2 className={styles.plainTitle}>Sources</h2>
        <p className={styles.plainLede}>
          The records a draft is checked against. Cachet verifies a quote or a citation
          only against material you add here, and refuses what it cannot trace to it.
          Nothing leaves this machine.
        </p>
      </div>

      {/* Add a record, filed into a project of your choosing. */}
      <div className={styles.sourceAdd}>
        <div className={styles.sourceAddRow}>
          <label className={styles.sourceProjectField}>
            <span className={styles.sourceProjectLabel}>File into</span>
            <select
              className={styles.sourceProjectSelect}
              value={project}
              disabled={!!upload}
              onChange={(e) => setProject((e.target as HTMLSelectElement).value)}
            >
              {projectChoices.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
              <option value={NEW_PROJECT}>＋ New project…</option>
            </select>
          </label>
          {project === NEW_PROJECT ? (
            <input
              type="text"
              className={styles.sourceProjectInput}
              placeholder="Project name"
              value={newProject}
              disabled={!!upload}
              aria-label="New project name"
              onInput={(e) => setNewProject((e.target as HTMLInputElement).value)}
            />
          ) : null}
        </div>

        <label
          className={styles.dropzone}
          data-busy={upload ? "true" : undefined}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void onFiles(e.dataTransfer?.files);
          }}
        >
          <input
            type="file"
            accept=".pdf,.docx,.txt"
            className={styles.dropzoneInput}
            disabled={!!upload}
            onChange={(e) => void onFiles((e.target as HTMLInputElement).files)}
          />
          {upload ? (
            <span className={styles.dropzoneState}>
              Reading {upload.filename}
              {upload.fraction < 1 ? ` ${Math.round(upload.fraction * 100)}%` : "…"}
            </span>
          ) : (
            <span className={styles.dropzoneState}>
              Add a record to <strong>{targetProject}</strong>: drop a PDF or Word file, or
              click to choose
            </span>
          )}
        </label>
        {error ? <p className={styles.sourceError}>{error}</p> : null}
      </div>

      {/* The library: everything you have added, grouped by project. */}
      <div className={styles.sourceLibrary}>
        {docs === null ? (
          <p className={styles.sourceLibraryNote}>Loading your records…</p>
        ) : docs.length === 0 ? (
          <p className={styles.sourceLibraryNote}>
            No records yet. Add one above and it will appear here.
          </p>
        ) : (
          groups.map((group) => (
            <div key={group.project} className={styles.sourceGroup}>
              <div className={styles.sourceGroupHead}>
                <span className={styles.sourceGroupName}>{group.project}</span>
                <span className={styles.sourceGroupCount}>
                  {group.items.length} {group.items.length === 1 ? "record" : "records"}
                </span>
              </div>
              <ul className={styles.sourceList}>
                {group.items.map((doc) => {
                  const isActive = active?.docId === doc.id;
                  const meta = metaLine(doc);
                  return (
                    <li
                      key={doc.id}
                      className={styles.sourceRow}
                      data-active={isActive ? "true" : undefined}
                    >
                      <span className={styles.sourceRowDot} aria-hidden="true" />
                      <div className={styles.sourceRowMain}>
                        <span className={styles.sourceRowName} title={doc.filename}>
                          {doc.filename}
                        </span>
                        {meta ? <span className={styles.sourceRowMeta}>{meta}</span> : null}
                      </div>
                      <div className={styles.sourceRowActions}>
                        <label className={styles.sourceMove}>
                          <span className={styles.srOnly}>Move {doc.filename} to project</span>
                          <select
                            className={styles.sourceMoveSelect}
                            value={doc.project}
                            onChange={(e) =>
                              void onMove(doc, (e.target as HTMLSelectElement).value)
                            }
                          >
                            {[...new Set([doc.project, ...projectChoices])].map((p) => (
                              <option key={p} value={p}>
                                {p}
                              </option>
                            ))}
                          </select>
                        </label>
                        {isActive ? (
                          <span className={styles.sourceActive}>Verifying against this</span>
                        ) : (
                          <button
                            type="button"
                            className={styles.sourceUse}
                            onClick={() => setActiveRecord(doc)}
                          >
                            Use as record
                          </button>
                        )}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </div>
          ))
        )}

        {active ? (
          <button type="button" className={styles.sourceClearActive} onClick={() => clearSource()}>
            Clear the active record
          </button>
        ) : null}
        {loadError ? <p className={styles.sourceError}>{loadError}</p> : null}
      </div>
    </section>
  );
}
