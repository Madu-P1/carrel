import { fireEvent, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { documents as documentsApi, type DocumentRow } from "@/services/api/endpoints";

import { SourcesView } from "./SourcesView";
import { loadedSource, sourceDocs, sourceUpload, sourcesError } from "./source";

// Sources is a data-fetching library view; mock the documents endpoints so the test
// drives load/empty/list/use/move deterministically. Design-system primitives render
// for real (jsdom), matching the house component-test convention.
vi.mock("@/services/api/endpoints", () => ({
  documents: {
    list: vi.fn(),
    upload: vi.fn(),
    setSubject: vi.fn()
  }
}));

const mockList = vi.mocked(documentsApi.list);
const mockSetSubject = vi.mocked(documentsApi.setSubject);

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
  // The Sources signals are module-global; reset them so tests stay isolated.
  sourceDocs.value = null;
  loadedSource.value = null;
  sourceUpload.value = null;
  sourcesError.value = null;
});

describe("SourcesView", () => {
  it("shows the empty state when no records exist", async () => {
    mockList.mockResolvedValue([]);
    render(<SourcesView />);
    expect(await screen.findByText(/No records yet/)).toBeTruthy();
  });

  it("lists uploaded records grouped by project (fixes 'I can't see it')", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Apex v. Northwind", page_count: 14 }),
      row({ id: "b", filename: "NDA.pdf", subject_name: "Sources", page_count: 6 })
    ]);
    render(<SourcesView />);
    expect(await screen.findByText("MSA.pdf")).toBeTruthy();
    expect(screen.getByText("NDA.pdf")).toBeTruthy();
    // The project name renders (as a group header, and as a move-select option).
    expect(screen.getAllByText("Apex v. Northwind").length).toBeGreaterThanOrEqual(1);
    // Meta line renders type + page count.
    expect(screen.getByText("PDF · 14 pages")).toBeTruthy();
  });

  it("marks the active record and switches it via 'Use as record'", async () => {
    mockList.mockResolvedValue([
      row({ id: "a", filename: "MSA.pdf" }),
      row({ id: "b", filename: "NDA.pdf" })
    ]);
    render(<SourcesView />);
    const useButtons = await screen.findAllByText("Use as record");
    expect(useButtons.length).toBe(2);
    fireEvent.click(useButtons[0]);
    expect(loadedSource.value?.docId).toBe("a");
    // The chosen row now reads as the active record.
    expect(await screen.findByText("Verifying against this")).toBeTruthy();
  });

  it("re-files a record into another project via the move select (the Vault filing)", async () => {
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Sources" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Apex" })
    ]);
    mockSetSubject.mockResolvedValue(row({ id: "a", subject_name: "Apex" }));
    mockList.mockResolvedValueOnce([
      row({ id: "a", filename: "MSA.pdf", subject_name: "Apex" }),
      row({ id: "b", filename: "Brief.pdf", subject_name: "Apex" })
    ]);
    render(<SourcesView />);
    await screen.findByText("MSA.pdf");
    const moveSelect = screen.getByLabelText(/Move MSA\.pdf to project/) as HTMLSelectElement;
    fireEvent.change(moveSelect, { target: { value: "Apex" } });
    expect(mockSetSubject).toHaveBeenCalledWith("a", "Apex");
  });

  it("offers a New project option that reveals a name input", async () => {
    mockList.mockResolvedValue([]);
    render(<SourcesView />);
    await screen.findByText(/No records yet/);
    const fileInto = screen.getByLabelText("File into") as HTMLSelectElement;
    fireEvent.change(fileInto, { target: { value: "__new__" } });
    expect(screen.getByPlaceholderText("Project name")).toBeTruthy();
  });
});
