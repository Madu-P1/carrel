import { act, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { describe, expect, it } from "vitest";

import {
  getFetchCalls,
  registerFetchHandler,
} from "../../../tests/support/mockFetch";
import { LibraryView } from "./LibraryView";

function rejectDocuments() {
  return registerFetchHandler((url, init) => {
    if (
      url.pathname === "/api/documents" &&
      init.method.toUpperCase() === "GET"
    ) {
      return new Response(
        JSON.stringify({ detail: "Failed to connect to database" }),
        { status: 500, headers: { "content-type": "application/json" } }
      );
    }
    return undefined;
  });
}

describe("LibraryView — error state", () => {
  it("shows a specific error heading and Retry control when the document fetch rejects", async () => {
    const unregister = rejectDocuments();
    try {
      render(<LibraryView />);
      await waitFor(() => {
        expect(screen.getByText("Library failed to load")).toBeTruthy();
      });
      expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
    } finally {
      unregister();
    }
  });

  it("clicking Retry re-dispatches a GET to /api/documents", async () => {
    const unregister = rejectDocuments();
    try {
      render(<LibraryView />);
      await waitFor(() => {
        expect(screen.getByRole("button", { name: /retry/i })).toBeTruthy();
      });

      const docCallsBefore = getFetchCalls().filter(
        (c) => c.url.includes("/api/documents") && c.method === "GET"
      ).length;

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: /retry/i }));
      });

      await waitFor(() => {
        expect(
          getFetchCalls().filter(
            (c) => c.url.includes("/api/documents") && c.method === "GET"
          ).length
        ).toBeGreaterThan(docCallsBefore);
      });
    } finally {
      unregister();
    }
  });
});
