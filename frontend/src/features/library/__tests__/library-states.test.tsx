import { signal } from "@preact/signals";
import { render, screen } from "@testing-library/preact";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentRow } from "@/services/api/endpoints";
import type { Query } from "@/lib/query";
import { useDocumentsQuery } from "../hooks/useDocumentsQuery";
import { LibraryView } from "../LibraryView";

vi.mock("../hooks/useDocumentsQuery", () => ({
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

describe("library-states — empty state", () => {
  it("renders data-testid=library-empty when fetch resolves with zero documents", () => {
    mockHook.mockReturnValue(makeQuery({ data: [] }));
    render(<LibraryView />);
    expect(screen.getByTestId("library-empty")).toBeTruthy();
  });
});

describe("library-states — error state", () => {
  it("renders data-testid=library-error when fetch rejects", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Network unavailable") })
    );
    render(<LibraryView />);
    expect(screen.getByTestId("library-error")).toBeTruthy();
  });

  it("surfaces the error message text — does not swallow it", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Network unavailable") })
    );
    render(<LibraryView />);
    const errorNode = screen.getByTestId("library-error");
    expect(errorNode.textContent).toContain("Network unavailable");
  });
});
