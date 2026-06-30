import { signal } from "@preact/signals";
import { render, screen } from "@testing-library/preact";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { DocumentDetail } from "@/services/api/endpoints";
import type { Query } from "@/lib/query";
import { useReaderDetail } from "./hooks/useReaderDetail";
import { ReaderDocumentViewForTests } from "./ReaderView";

vi.mock("./hooks/useReaderDetail", () => ({
  useReaderDetail: vi.fn(),
  resetReaderDetailQueries: vi.fn(),
  invalidateReaderDetailQuery: vi.fn(),
}));

const mockHook = vi.mocked(useReaderDetail);

function makeQuery(overrides: {
  data?: DocumentDetail | undefined;
  loading?: boolean;
  error?: Error | null;
  refetch?: () => Promise<void>;
}): Query<DocumentDetail> {
  return {
    data: signal<DocumentDetail | undefined>(overrides.data),
    loading: signal(overrides.loading ?? false),
    error: signal<Error | null>(overrides.error ?? null),
    refetch: overrides.refetch ?? (async () => {}),
    reset: () => {},
    subscribe: () => () => {},
  };
}

const EMPTY_DOC = {
  document: { id: "doc-empty", filename: "contract.txt", file_type: "txt" },
  summary: "",
  chunks: [],
} as unknown as DocumentDetail;

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ReaderDocumentView — loading state", () => {
  it("renders a loading indicator while the document is in-flight", () => {
    mockHook.mockReturnValue(makeQuery({ loading: true }));
    render(<ReaderDocumentViewForTests id="doc-a" />);
    expect(screen.getByRole("status")).toBeTruthy();
  });
});

describe("ReaderDocumentView — fetch-failure state", () => {
  it("renders a specific error heading when the document fetch fails", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Network failure: could not reach document endpoint") })
    );
    render(<ReaderDocumentViewForTests id="doc-b" />);
    expect(screen.getByText(/reader preview failed to load/i)).toBeTruthy();
  });

  it("renders the specific error reason in the failure state", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Network failure: could not reach document endpoint") })
    );
    render(<ReaderDocumentViewForTests id="doc-b" />);
    expect(screen.getByText(/network failure/i)).toBeTruthy();
  });

  it("renders a retry control in the failure state", () => {
    mockHook.mockReturnValue(
      makeQuery({ error: new Error("Server error") })
    );
    render(<ReaderDocumentViewForTests id="doc-b" />);
    expect(screen.getByRole("button", { name: /reload the document/i })).toBeTruthy();
  });
});

describe("ReaderDocumentView — empty-content state", () => {
  it("renders an empty-content heading when the document has no extractable text", () => {
    mockHook.mockReturnValue(makeQuery({ data: EMPTY_DOC }));
    render(<ReaderDocumentViewForTests id="doc-empty" />);
    expect(screen.getByText(/no readable content/i)).toBeTruthy();
  });

  it("does not render error copy in the empty-content state", () => {
    mockHook.mockReturnValue(makeQuery({ data: EMPTY_DOC }));
    render(<ReaderDocumentViewForTests id="doc-empty" />);
    expect(screen.queryByText(/failed to load/i)).toBeNull();
  });
});
