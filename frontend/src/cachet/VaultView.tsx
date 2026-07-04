import { useEffect, useRef, useState } from "preact/hooks";

import { Button, Dialog, showToast, toast } from "@/design-system";
import { apiErrorMessage } from "@/services/api/client";

import { FolderMark } from "./FolderMark";
import { VaultMark } from "./VaultMark";
import { openExamination } from "./examine/examineStore";

import {
  DEFAULT_PROJECT,
  clearPersistedActiveRecord,
  clearSource,
  createVault,
  deleteDocument,
  deleteVault,
  knownProjects,
  loadedSource,
  refreshSources,
  refreshVaults,
  setDocumentProject,
  sourceDocs,
  sourceUpload,
  setActiveRecord,
  sourcesError,
  sourcesFixtureRequested,
  uploadSource,
  type SourceDoc
} from "./source";
import styles from "./cachet.module.css";

/**
 * Vault: a grid of vaults (document folders), each a card with the solid folder
 * as its face. Open a vault to see and manage the records filed in it. The records
 * are what Cachet checks a draft against; pick one as the active record, move it
 * between vaults, or delete it. On-device: nothing leaves the machine.
 *
 * The folder concept is "vault" in the UI; internally it still maps to the engine's
 * `subject_name` (carried as the `project` identifier).
 */

function metaLine(doc: SourceDoc): string {
  const bits: string[] = [];
  if (doc.fileType) bits.push(doc.fileType.toUpperCase());
  if (typeof doc.pageCount === "number" && doc.pageCount > 0) {
    bits.push(`${doc.pageCount} ${doc.pageCount === 1 ? "page" : "pages"}`);
  }
  return bits.join(" · ");
}

function recordCount(n: number): string {
  return `${n} ${n === 1 ? "record" : "records"}`;
}

// A quiet ink glyph for the "Add a record" action, in the rail's hand-set stroke
// language so it sits beside the folder marks without borrowing an icon set.
const UPLOAD_GLYPH = (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
    <path d="M6 3.5h7l5 5v12H6z" />
    <path d="M13 3.5V9h5" />
    <path d="M12 18v-6M9.5 14l2.5-2.5L14.5 14" />
  </svg>
);

export function VaultView() {
  const [error, setError] = useState<string | null>(null);
  // The vault currently opened (its records shown), or null for the grid.
  const [openVault, setOpenVault] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  // The record awaiting a delete confirmation, or null. Delete is an irreversible
  // cascade, so it always passes through the confirm dialog below.
  const [pendingDelete, setPendingDelete] = useState<SourceDoc | null>(null);
  const [deleting, setDeleting] = useState(false);
  // Folder-first vault creation: the inline "New vault" name input.
  const [creatingVault, setCreatingVault] = useState(false);
  const [newVaultName, setNewVaultName] = useState("");
  const [vaultBusy, setVaultBusy] = useState(false);
  // Moving a record always passes through a destination-naming confirm (a misfile
  // points Cachet at the wrong matter), so neither the picker nor a drag ever moves
  // silently. Drag is only an accelerator that pre-fills the same confirm.
  const [pendingMove, setPendingMove] = useState<{ doc: SourceDoc; to: string } | null>(null);
  const [moving, setMoving] = useState(false);
  const [draggingId, setDraggingId] = useState<string | null>(null);
  const [dragOverVault, setDragOverVault] = useState<string | null>(null);
  // Where focus lands after a delete: the deleted row's button is gone, so we steer
  // focus to the always-present "All vaults" back link rather than letting it fall
  // to <body> (the Dialog otherwise restores focus to the now-detached trigger).
  const backRef = useRef<HTMLButtonElement | null>(null);

  const docs = sourceDocs.value;
  const upload = sourceUpload.value;
  const active = loadedSource.value;
  const loadError = sourcesError.value;

  useEffect(() => {
    // Dev-only visual fixture. The DEV gate is load-bearing: this branch sets
    // `loadedSource`, whose subscriber persists to localStorage, so in a
    // production build a single ?fixture=sources visit would leave a FAKE
    // executed contract as the active record for later real sessions — the
    // lectern would assert "loaded as the record" about a document that does
    // not exist. import.meta.env.DEV is statically false in the production
    // bundle, so the fixture (and its fake filenames) is compiled out.
    if (import.meta.env.DEV && sourcesFixtureRequested(globalThis.location?.search ?? "")) {
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
      clearPersistedActiveRecord();
      return;
    }
    void refreshSources();
    void refreshVaults();
  }, []);

  // If the open vault disappears (its last record was moved or deleted out of an
  // implicit, unregistered vault), fall back to the grid rather than stranding the
  // user in the detail view of a vault that no longer exists. A registry vault
  // persists when emptied, so opening one and clearing it keeps you in its detail.
  useEffect(() => {
    if (openVault && !knownProjects().includes(openVault)) setOpenVault(null);
  }, [openVault, docs]);

  const projectChoices = knownProjects();

  // Vault identity is case-insensitive, so map any record's subject to the one
  // canonical spelling (from projectChoices). Without this, a record filed under
  // "general" would form a second card next to the "General" folder.
  const canonicalOf = new Map<string, string>();
  for (const name of projectChoices) canonicalOf.set(name.toLowerCase(), name);
  const canon = (project: string): string => {
    const value = project || DEFAULT_PROJECT;
    return canonicalOf.get(value.toLowerCase()) ?? value;
  };

  // Records grouped by their canonical vault, alongside the registry-aware list.
  const byVault = new Map<string, SourceDoc[]>();
  for (const d of docs ?? []) {
    const key = canon(d.project);
    const bucket = byVault.get(key);
    if (bucket) bucket.push(d);
    else byVault.set(key, [d]);
  }
  const allVaults = projectChoices.map((name) => ({ name, items: byVault.get(name) ?? [] }));
  // Hide an EMPTY default ("General") once another vault exists, so the grid is not
  // cluttered by an always-present empty default. When it is the only vault and holds
  // nothing, the explicit empty state below covers the "no vaults yet" case.
  const vaults = allVaults.filter((v) => v.items.length > 0 || v.name !== DEFAULT_PROJECT);
  const q = query.trim().toLowerCase();
  const shownVaults = q ? vaults.filter((v) => v.name.toLowerCase().includes(q)) : vaults;
  const openItems = openVault ? (byVault.get(openVault) ?? []) : [];

  async function onFiles(files: FileList | null | undefined, targetVault: string) {
    const file = files && files[0];
    if (!file || upload) return;
    setError(null);
    try {
      await uploadSource(file, targetVault);
    } catch (e) {
      setError(apiErrorMessage(e, "The document could not be loaded.") ?? "The document could not be loaded.");
    }
  }

  // Moving never happens on the gesture. The picker and a drag both land here, which
  // opens the destination-naming confirm below. A misfile points Cachet at the wrong
  // matter, so the user always reads where the record is going before it goes.
  function requestMove(doc: SourceDoc, to: string) {
    // Compare case-insensitively so re-selecting the record's own vault (under a
    // different casing) is a no-op, not a spurious move confirm.
    if (!to || to.toLowerCase() === doc.project.toLowerCase()) return;
    setPendingMove({ doc, to });
  }

  async function onConfirmMove() {
    const move = pendingMove;
    if (!move) return;
    const { doc, to } = move;
    const from = doc.project;
    setMoving(true);
    try {
      await setDocumentProject(doc.id, to);
      setPendingMove(null);
      showToast({
        title: `Moved ${doc.filename} to ${to}`,
        kind: "success",
        action: {
          label: "Undo",
          onClick: () => {
            void setDocumentProject(doc.id, from).catch((e) =>
              toast.error("Could not undo the move", apiErrorMessage(e))
            );
          }
        },
        durationMs: 7000
      });
    } catch (e) {
      toast.error("Could not move the record", apiErrorMessage(e));
    } finally {
      setMoving(false);
    }
  }

  async function onConfirmDelete() {
    const doc = pendingDelete;
    if (!doc) return;
    setDeleting(true);
    try {
      await deleteDocument(doc.id);
      toast.success(`Deleted ${doc.filename}.`);
      setPendingDelete(null);
      // After the dialog closes it would restore focus to the deleted row's button,
      // which no longer exists, so focus falls to <body>. Steer it to the back link
      // on the next frame, after the dialog's own focus-restore has run.
      requestAnimationFrame(() => backRef.current?.focus());
    } catch (e) {
      toast.error("Could not delete the record", apiErrorMessage(e));
    } finally {
      setDeleting(false);
    }
  }

  async function onCreateVault(event: Event) {
    event.preventDefault();
    const name = newVaultName.trim();
    if (!name || vaultBusy) return;
    setVaultBusy(true);
    setError(null);
    try {
      await createVault(name);
      setNewVaultName("");
      setCreatingVault(false);
    } catch (e) {
      setError(apiErrorMessage(e, "The vault could not be created.") ?? "The vault could not be created.");
    } finally {
      setVaultBusy(false);
    }
  }

  async function onDeleteVault(name: string) {
    setError(null);
    try {
      await deleteVault(name);
      toast.success(`Deleted the ${name} vault.`);
      if (openVault === name) setOpenVault(null);
    } catch (e) {
      toast.error("Could not delete the vault", apiErrorMessage(e));
    }
  }

  // ---- The opened vault: its records, scoped upload, move, delete. ----
  function renderDetail(name: string) {
    // The other vaults a record here can be dragged into. Drag is the accelerator;
    // the per-row picker is the equivalent keyboard path (WCAG 2.5.7).
    const moveTargets = projectChoices.filter((p) => p !== name);
    return (
      <div className={styles.vaultDetail}>
        <button
          type="button"
          ref={backRef}
          className={styles.vaultBack}
          onClick={() => setOpenVault(null)}
        >
          ← All vaults
        </button>
        <div className={styles.vaultDetailHead}>
          <FolderMark width={34} className={styles.vaultDetailMark} />
          <h2 className={styles.vaultDetailName}>{name}</h2>
          <span className={styles.sourceGroupCount}>{recordCount(openItems.length)}</span>
          {openItems.length === 0 && name !== DEFAULT_PROJECT ? (
            <button
              type="button"
              className={styles.vaultDelete}
              onClick={() => void onDeleteVault(name)}
              aria-label={`Delete the ${name} vault`}
            >
              Delete vault
            </button>
          ) : null}
        </div>

        <label
          className={styles.dropzone}
          data-busy={upload ? "true" : undefined}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            void onFiles(e.dataTransfer?.files, name);
          }}
        >
          <input
            type="file"
            accept=".pdf,.docx,.txt,.md"
            className={styles.dropzoneInput}
            disabled={!!upload}
            onChange={(e) => void onFiles((e.target as HTMLInputElement).files, name)}
          />
          {/* One stable live region: its text swaps between the idle prompt and
              the read-progress, so a screen reader announces the progress. */}
          <span className={styles.dropzoneState} aria-live="polite">
            {upload ? (
              <>
                Reading {upload.filename}
                {upload.fraction < 1 ? ` ${Math.round(upload.fraction * 100)}%` : "…"}
              </>
            ) : (
              <>
                Add a record to <strong>{name}</strong>: drop a PDF or Word file, or click to choose
              </>
            )}
          </span>
        </label>
        {error ? (
          <p className={styles.sourceError} role="alert">
            {error}
          </p>
        ) : null}

        {openItems.length === 0 ? (
          <p className={styles.vaultEmpty}>No records yet. Add one above.</p>
        ) : (
          <ul className={styles.sourceList}>
            {openItems.map((doc) => {
              const isActive = active?.docId === doc.id;
              const meta = metaLine(doc);
              return (
                <li
                  key={doc.id}
                  className={styles.sourceRow}
                  data-active={isActive ? "true" : undefined}
                  data-dragging={draggingId === doc.id ? "true" : undefined}
                  draggable
                  onDragStart={(e) => {
                    setDraggingId(doc.id);
                    if (e.dataTransfer) {
                      e.dataTransfer.effectAllowed = "move";
                      e.dataTransfer.setData("text/plain", doc.id);
                    }
                  }}
                  onDragEnd={() => {
                    setDraggingId(null);
                    setDragOverVault(null);
                  }}
                >
                  <span className={styles.sourceRowDot} aria-hidden="true" />
                  <div className={styles.sourceRowMain}>
                    <button
                      type="button"
                      className={styles.sourceRowName}
                      title={`Open ${doc.filename}`}
                      onClick={() =>
                        openExamination({
                          docId: doc.id,
                          filename: doc.filename,
                          fileType: doc.fileType
                        })
                      }
                    >
                      {doc.filename}
                    </button>
                    {meta ? <span className={styles.sourceRowMeta}>{meta}</span> : null}
                  </div>
                  <div className={styles.sourceRowActions}>
                    <label className={styles.sourceMove}>
                      <span className={styles.srOnly}>Move {doc.filename} to vault</span>
                      <select
                        className={styles.sourceMoveSelect}
                        value={canon(doc.project)}
                        onChange={(e) => requestMove(doc, (e.target as HTMLSelectElement).value)}
                      >
                        {projectChoices.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      className={styles.sourceUse}
                      onClick={() =>
                        openExamination({
                          docId: doc.id,
                          filename: doc.filename,
                          fileType: doc.fileType
                        })
                      }
                    >
                      Open the record
                    </button>
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
                    <button
                      type="button"
                      className={styles.sourceDelete}
                      onClick={() => setPendingDelete(doc)}
                      aria-label={`Delete ${doc.filename}`}
                    >
                      Delete
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}

        {openItems.length > 0 && moveTargets.length > 0 ? (
          <div className={styles.moveRail} data-dragging={draggingId ? "true" : undefined}>
            <span className={styles.moveRailLabel}>
              {draggingId ? "Drop on a vault to move" : "Drag a record onto a vault to move it"}
            </span>
            <div className={styles.moveRailChips}>
              {moveTargets.map((target) => (
                <div
                  key={target}
                  className={styles.moveChip}
                  data-over={dragOverVault === target ? "true" : undefined}
                  onDragOver={(e) => {
                    if (!draggingId) return;
                    e.preventDefault();
                    if (e.dataTransfer) e.dataTransfer.dropEffect = "move";
                    setDragOverVault(target);
                  }}
                  onDragLeave={() => setDragOverVault((v) => (v === target ? null : v))}
                  onDrop={(e) => {
                    e.preventDefault();
                    const doc = openItems.find((d) => d.id === draggingId);
                    setDragOverVault(null);
                    setDraggingId(null);
                    if (doc) requestMove(doc, target);
                  }}
                >
                  <FolderMark width={20} className={styles.moveChipMark} />
                  <span className={styles.moveChipName}>{target}</span>
                </div>
              ))}
            </div>
          </div>
        ) : null}

        {active ? (
          <button type="button" className={styles.sourceClearActive} onClick={() => clearSource()}>
            Clear the active record
          </button>
        ) : null}
      </div>
    );
  }

  // ---- The grid: action cards, search, and a card per vault. ----
  function renderGrid() {
    return (
      <>
        <div className={styles.plainHead}>
          <div className={styles.vaultTitleRow}>
            <VaultMark size={42} tone="oxblood" className={styles.vaultTitleMark} title="" />
            <h2 className={styles.plainTitle}>Vault</h2>
          </div>
          <p className={styles.plainLede}>
            The records Cachet checks a draft against, filed in vaults. Nothing leaves this machine.
          </p>
        </div>

        <div className={styles.vaultActions}>
          <button
            type="button"
            className={styles.vaultActionCard}
            onClick={() => setCreatingVault(true)}
          >
            <span className={styles.vaultActionIcon}>
              <VaultMark size={30} title="" />
            </span>
            <span className={styles.vaultActionText}>
              <span className={styles.vaultActionTitle}>Create vault</span>
              <span className={styles.vaultActionDesc}>Start a folder to file records into.</span>
            </span>
          </button>
          <label className={styles.vaultActionCard} data-busy={upload ? "true" : undefined}>
            <input
              type="file"
              accept=".pdf,.docx,.txt,.md"
              className={styles.dropzoneInput}
              disabled={!!upload}
              onChange={(e) => void onFiles((e.target as HTMLInputElement).files, DEFAULT_PROJECT)}
            />
            <span className={`${styles.vaultActionIcon} ${styles.vaultActionGlyph}`}>
              {UPLOAD_GLYPH}
            </span>
            <span className={styles.vaultActionText}>
              <span className={styles.vaultActionTitle}>Add a record</span>
              <span className={styles.vaultActionDesc}>
                {upload
                  ? `Reading ${upload.filename}…`
                  : "Upload a contract, PDF, or Word file."}
              </span>
            </span>
          </label>
        </div>

        {creatingVault ? (
          <form className={styles.vaultCreateForm} onSubmit={(e) => void onCreateVault(e)}>
            <input
              type="text"
              className={styles.vaultCreateInput}
              placeholder="Vault name"
              aria-label="Name a new vault"
              autofocus
              value={newVaultName}
              disabled={vaultBusy}
              onInput={(e) => setNewVaultName((e.target as HTMLInputElement).value)}
            />
            <button
              type="submit"
              className={styles.vaultCreateGo}
              disabled={vaultBusy || !newVaultName.trim()}
            >
              Create
            </button>
            <button
              type="button"
              className={styles.vaultCreateCancel}
              onClick={() => {
                setCreatingVault(false);
                setNewVaultName("");
              }}
            >
              Cancel
            </button>
          </form>
        ) : null}
        {error ? (
          <p className={styles.sourceError} role="alert">
            {error}
          </p>
        ) : null}

        <div className={styles.vaultFilter}>
          <input
            type="search"
            className={styles.vaultSearch}
            placeholder="Search vaults"
            aria-label="Search vaults"
            value={query}
            onInput={(e) => setQuery((e.target as HTMLInputElement).value)}
          />
        </div>

        {docs === null ? (
          <p className={styles.sourceLibraryNote} data-testid="vault-list-loading">
            Loading vaults…
          </p>
        ) : loadError ? (
          <div className={styles.sourceError} role="alert" data-testid="vault-list-error">
            <p className={styles.vaultEmpty}>Couldn't load your vaults.</p>
            <p>{loadError}</p>
            <Button variant="ghost" onClick={() => void refreshSources()}>
              Try again
            </Button>
          </div>
        ) : shownVaults.length === 0 ? (
          q ? (
            <p className={styles.sourceLibraryNote}>No vaults match that search.</p>
          ) : (
            <div className={styles.sourceLibraryNote} data-testid="vault-list-empty">
              <p className={styles.vaultEmpty}>No vaults yet</p>
              <p>Create a vault to organize the documents you verify.</p>
            </div>
          )
        ) : (
          <div className={styles.vaultGrid}>
            {shownVaults.map((vault) => {
              const holdsActive =
                active != null && vault.items.some((d) => d.id === active.docId);
              return (
                <div key={vault.name} className={styles.vaultCard}>
                  <button
                    type="button"
                    className={styles.vaultCardThumb}
                    onClick={() => setOpenVault(vault.name)}
                    aria-label={`Open the ${vault.name} vault`}
                  >
                    <FolderMark width={56} className={styles.vaultCardMark} />
                  </button>
                  <div className={styles.vaultCardMeta}>
                    <span className={styles.vaultCardName} title={vault.name}>
                      {vault.name}
                      {holdsActive ? (
                        <span className={styles.vaultCardDot} aria-label="holds the active record" />
                      ) : null}
                    </span>
                    <span className={styles.vaultCardCount}>{recordCount(vault.items.length)}</span>
                  </div>
                  {vault.items.length === 0 && vault.name !== DEFAULT_PROJECT ? (
                    <button
                      type="button"
                      className={styles.vaultCardDelete}
                      onClick={() => void onDeleteVault(vault.name)}
                      aria-label={`Delete the ${vault.name} vault`}
                    >
                      Delete vault
                    </button>
                  ) : null}
                </div>
              );
            })}
          </div>
        )}

        <p className={styles.vaultProvenance}>
          <span className={styles.vaultProvenanceDot} aria-hidden="true" />
          Every source is hashed when loaded and stays on this machine. Nothing leaves it.
        </p>
      </>
    );
  }

  return (
    <section className={`${styles.plainView} ${styles.sourcesView}`}>
      {openVault ? renderDetail(openVault) : renderGrid()}

      <Dialog
        open={pendingDelete !== null}
        title="Delete this record?"
        description={
          pendingDelete
            ? `${pendingDelete.filename} and everything Cachet read from it will be removed from this machine. This cannot be undone.`
            : undefined
        }
        onClose={() => {
          if (!deleting) setPendingDelete(null);
        }}
        actions={
          <>
            <Button variant="ghost" onClick={() => setPendingDelete(null)} disabled={deleting}>
              Keep
            </Button>
            <Button variant="danger" onClick={() => void onConfirmDelete()} isLoading={deleting}>
              Delete
            </Button>
          </>
        }
      />

      <Dialog
        open={pendingMove !== null}
        title="Move this record?"
        description={
          pendingMove
            ? `${pendingMove.doc.filename} moves from ${pendingMove.doc.project} to ${pendingMove.to}. Cachet checks a draft against the vault its record sits in, so filing it correctly keeps your matters apart.`
            : undefined
        }
        onClose={() => {
          if (!moving) setPendingMove(null);
        }}
        actions={
          <>
            <Button variant="ghost" onClick={() => setPendingMove(null)} disabled={moving}>
              Keep here
            </Button>
            <Button variant="primary" onClick={() => void onConfirmMove()} isLoading={moving}>
              Move to {pendingMove?.to}
            </Button>
          </>
        }
      >
        {pendingMove && active?.docId === pendingMove.doc.id ? (
          <p className={styles.moveActiveNote}>
            This is your active record. It stays the one Cachet verifies against after the move.
          </p>
        ) : null}
      </Dialog>
    </section>
  );
}
