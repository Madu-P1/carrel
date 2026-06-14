import { fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  documents as documentsApi,
  vaults as vaultsApi,
  type DocumentRow
} from "@/services/api/endpoints";

import { VaultView } from "./VaultView";
import { loadedSource, sourceDocs, sourceUpload, sourcesError, vaultNames } from "./source";

// Vault is a data-fetching library view; mock the documents + vaults endpoints so
// the test drives load/empty/list/use/move/delete/create deterministically.
// Design-system primitives render for real (jsdom), matching the house convention.
vi.mock("@/services/api/endpoints", () => ({
  documents: {
    list: vi.fn(),
    upload: vi.fn(),
    setSubject: vi.fn(),
    delete: vi.fn()
  },
  vaults: {
    list: vi.fn().mockResolvedValue({ vaults: [] }),
    create: vi.fn(),
    remove: vi.fn()
  }
}));

const mockList = vi.mocked(documentsApi.list);
const mockSetSubject = vi.mocked(documentsApi.setSubject);
const mockDelete = vi.mocked(documentsApi.delete);
const mockVaultsList = vi.mocked(vaultsApi.list);
const mockVaultsCreate = vi.mocked(vaultsApi.create);

function row(overrides: Partial<DocumentRow> = {}): DocumentRow {
  return {
    id: "d1",
    filename: "Contract.pdf",
    subject_name: "Sources",
    file_type: "pdf",
    upload_date: null,
    page_count: 5,
    status: "ready",
    ...overrides
  } as DocumentRow;
}

afterEach(() => {
  vi.clearAllMocks();
  // clearAllMocks keeps implementations; restore the default vaults.list resolution.
  mockVaultsList.mockResolvedValue({ vaults: [] });
  // The Vault signals are module-global; reset them so tests stay isolated.
  sourceDocs.value = null;
  loadedSource.value = null;
  sourceUpload.value = null;
  sourcesError.value = null;
  vaultNames.value = null;
});

describe("VaultView grid", () => {
  it("shows a card per vault with its record count, hiding records until opened", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Apex v. Northwind", page_count: 14 }),
      row({ id: "b", filename: "NDA.pdf", subject_name: "Henderson Matter", page_count: 6 })
    ]);
    render(<VaultView />);
    expect(await screen.findByText("Apex v. Northwind")).toBeTruthy();
    expect(screen.getByText("Henderson Matter")).toBeTruthy();
    expect(screen.getAllByText("1 record").length).toBe(2);
    // Records live inside an opened vault, never on the grid.
    expect(screen.queryByText("MSA.pdf")).toBeNull();
  });

  it("shows an empty vault from the registry as a card (folder-first)", async () => {
    mockList.mockResolvedValue([]);
    mockVaultsList.mockResolvedValue({ vaults: ["Apex v. Northwind"] });
    render(<VaultView />);
    expect(await screen.findByText("Apex v. Northwind")).toBeTruthy();
    expect(screen.getByText("0 records")).toBeTruthy();
  });

  it("creates a vault from the Create vault action", async () => {
    mockList.mockResolvedValue([]);
    mockVaultsCreate.mockResolvedValue({ vaults: ["Henderson Matter"] });
    render(<VaultView />);
    fireEvent.click(await screen.findByText("Create vault"));
    fireEvent.input(screen.getByLabelText("Name a new vault"), {
      target: { value: "Henderson Matter" }
    });
    fireEvent.click(screen.getByText("Create"));
    await waitFor(() => expect(mockVaultsCreate).toHaveBeenCalledWith("Henderson Matter"));
  });

  it("treats vault names case-insensitively (no duplicate card for a case variant)", async () => {
    mockList.mockResolvedValue([row({ id: "a", filename: "MSA.pdf", subject_name: "general" })]);
    mockVaultsList.mockResolvedValue({ vaults: ["General"] });
    render(<VaultView />);
    await screen.findByText("General");
    // One card, the registry spelling, holding the record filed under "general".
    expect(screen.getAllByText("General").length).toBe(1);
    expect(screen.getByText("1 record")).toBeTruthy();
    expect(screen.queryByText("general")).toBeNull();
  });

  it("filters the grid by the search box", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Apex v. Northwind" }),
      row({ id: "b", filename: "NDA.pdf", subject_name: "Henderson Matter" })
    ]);
    render(<VaultView />);
    await screen.findByText("Apex v. Northwind");
    fireEvent.input(screen.getByLabelText("Search vaults"), { target: { value: "hender" } });
    expect(screen.queryByText("Apex v. Northwind")).toBeNull();
    expect(screen.getByText("Henderson Matter")).toBeTruthy();
  });
});

describe("VaultView opened vault", () => {
  async function openVault(name: string) {
    fireEvent.click(await screen.findByLabelText(`Open the ${name} vault`));
  }

  it("opens a vault to its records and marks the active record via Use as record", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Matter" }),
      row({ id: "b", filename: "NDA.pdf", subject_name: "Matter" })
    ]);
    render(<VaultView />);
    await openVault("Matter");
    const useButtons = await screen.findAllByText("Use as record");
    expect(useButtons.length).toBe(2);
    fireEvent.click(useButtons[0]);
    expect(loadedSource.value?.docId).toBe("a");
    expect(await screen.findByText("Verifying against this")).toBeTruthy();
  });

  it("opens a record in the examiner when its name is clicked, not only the Open button", async () => {
    const { examination } = await import("./examine/examineStore");
    examination.value = null;
    mockList.mockResolvedValue([
      row({ id: "d7", filename: "Lease.pdf", subject_name: "Matter", file_type: "pdf" })
    ]);
    render(<VaultView />);
    await openVault("Matter");
    // The filename itself is the click target (its own button, accessible name
    // = the filename, with an "Open <name>" hover title), so "click a document
    // in the vault to see it" works without hunting for the separate Open button.
    fireEvent.click(await screen.findByRole("button", { name: "Lease.pdf" }));
    expect(examination.value).toEqual({ docId: "d7", filename: "Lease.pdf", fileType: "pdf" });
  });

  it("re-files a record via the move picker, but only after the destination confirm", async () => {
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Matter" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Other" })
    ]);
    mockSetSubject.mockResolvedValue(row({ id: "a", subject_name: "Other" }));
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Other" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Other" })
    ]);
    render(<VaultView />);
    await openVault("Matter");
    await screen.findByText("MSA.pdf");
    const moveSelect = screen.getByLabelText(/Move MSA\.pdf to vault/) as HTMLSelectElement;
    fireEvent.change(moveSelect, { target: { value: "Other" } });
    // The gesture never moves the record; the destination-naming confirm does.
    expect(mockSetSubject).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/moves from Matter to Other/)).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Move to Other"));
    await waitFor(() => expect(mockSetSubject).toHaveBeenCalledWith("a", "Other"));
  });

  it("drags a record onto a vault chip, opening the same move confirm", async () => {
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Matter" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Other" })
    ]);
    mockSetSubject.mockResolvedValue(row({ id: "a", subject_name: "Other" }));
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Other" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Other" })
    ]);
    render(<VaultView />);
    await openVault("Matter");
    await screen.findByText("MSA.pdf");
    // Grab the rail by its at-rest hint, then find the "Other" drop chip inside it
    // (scoped so it does not collide with the per-row move picker options).
    const rail = screen.getByText(/Drag a record onto a vault/).parentElement as HTMLElement;
    const rowLi = screen.getByText("MSA.pdf").closest("li") as HTMLElement;
    fireEvent.dragStart(rowLi);
    fireEvent.drop(within(rail).getByText("Other"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText(/moves from Matter to Other/)).toBeTruthy();
    fireEvent.click(within(dialog).getByText("Move to Other"));
    await waitFor(() => expect(mockSetSubject).toHaveBeenCalledWith("a", "Other"));
  });

  it("deletes a record only after the confirm dialog (never on the row click)", async () => {
    mockList.mockResolvedValueOnce([row({ id: "a", filename: "MSA.pdf", subject_name: "Matter" })]);
    render(<VaultView />);
    await openVault("Matter");
    fireEvent.click(await screen.findByLabelText("Delete MSA.pdf"));
    expect(mockDelete).not.toHaveBeenCalled();
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete this record?")).toBeTruthy();

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mockDelete.mockResolvedValue({ deleted: true } as any);
    mockList.mockResolvedValueOnce([]); // the post-delete refresh
    fireEvent.click(within(dialog).getByText("Delete"));
    await waitFor(() => expect(mockDelete).toHaveBeenCalledWith("a"));
  });
});
