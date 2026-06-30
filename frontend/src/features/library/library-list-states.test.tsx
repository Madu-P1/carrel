import { signal } from "@preact/signals";
import { act, fireEvent, render, screen } from "@testing-library/preact";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentRow } from "@/services/api/endpoints";
import type { Query } from "@/lib/query";
import { useDocumentsQuery } from "./hooks/useDocumentsQuery";
import { LibraryView } from "./LibraryView";

vi.mock("./hooks/useDocumentsQuery", () => ({
  useDocumentsQuery: vi.fn(),
  resetDocumentsQuery: vi.fn(),
  notePendingImport: vi.fn(),
}));

const mockHook = vi.mocked(useDocumentsQuery);

function makeQuery(overrides: {
  data?: DocumentRow[] | undefined;
  loading?: boolean;
  error?: Error | null;
  refetch?: () => Promise<void>;
}): Query<DocumentRow[]> {
  return {
    data: signal<DocumentRow[] | undefined>(overrides.data),
    loading: signal(overrides.loading ?? false),
    error: signal<Error | null>(overrides.error ?? null),
    refetch: overrides.refetch ?? (async () => {}),
    reset: () => {},
    subscribe: () => () => {},
  };
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("LibraryView — loading state", () => {
  it("renders loading text while documents are in-flight", () => {
    mockHook.mockReturnValue(makeQuery({ loading: true }));
    render(<LibraryView />);
    expect(screen.getByText(/loading your documents/i)).toBeTruthy();
  });
});

describe("LibraryView — empty state", () => {
  it("renders 'No sources yet' when fetch succeeds with zero documents", () => {
    mockHook.mockReturnValue(makeQuery({ data: [] }));
    render(<LibraryView />);
    expect(screen.getByText(/no sources yet/i)).toBeTruthy();
  });

  it("does not render error copy in the empty state", () => {
    mockHook.mockReturnValue(makeQuery({ data: [] }));
    render(<LibraryView />);
    expect(screen.queryByText(/failed to load/i)).toBeNull();
  });
});

describe("LibraryView — error state", () => {
  it("renders failure heading and specific error reason when fetch fails", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Connection refused") })
    );
    render(<LibraryView />);
    expect(screen.getByText(/library failed to load/i)).toBeTruthy();
    expect(screen.getByText(/connection refused/i)).toBeTruthy();
  });

  it("renders a retry control in the error state", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Server error") })
    );
    render(<LibraryView />);
    expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
  });

  it("clicking retry calls the hook's refetch", () => {
    const refetch = vi.fn(async () => {});
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Server error"), refetch })
    );
    render(<LibraryView />);
    act(() => {
      fireEvent.click(screen.getByRole("button", { name: /retry/i }));
    });
    expect(refetch).toHaveBeenCalledOnce();
  });
});
