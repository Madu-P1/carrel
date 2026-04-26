import { act, cleanup, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test } from "vitest";

import { StudyView } from "@/features/study/StudyView";
import { mockJson } from "../support/mockFetch";

afterEach(() => {
  cleanup();
});

describe("StudyView", () => {
  test("empty due queue shows 'caught up' intro and disabled start button", async () => {
    mockJson("GET", "/api/srs/due", { cards: [] });
    render(<StudyView />);
    // Wait for the query to settle.
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });
    expect(screen.getByText(/You.*caught up/i)).toBeTruthy();
    const startButton = screen.getByRole("button", { name: /Start a session/i });
    expect((startButton as HTMLButtonElement).disabled).toBe(true);
  });

  test("populated queue shows due count", async () => {
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "card-1",
          front: "What is mitosis?",
          back: "Cell division producing two genetically identical daughter cells.",
          state: "review",
          stability: 2.2,
          difficulty: 0.3,
          reps: 1,
          lapses: 0,
          due_date: "2026-04-21",
          concept: "Mitosis",
          document_name: "biology.pdf",
          subject_name: "Biology"
        },
        {
          id: "card-2",
          front: "What is meiosis?",
          back: "Gamete-producing division creating four haploid cells.",
          state: "review",
          stability: 1.8,
          difficulty: 0.4,
          reps: 0,
          lapses: 0,
          due_date: "2026-04-21",
          concept: "Meiosis",
          document_name: "biology.pdf",
          subject_name: "Biology"
        }
      ]
    });
    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });
    expect(screen.getByText(/2 cards due/i)).toBeTruthy();
    const startButton = screen.getByRole("button", { name: /Start a session/i });
    expect((startButton as HTMLButtonElement).disabled).toBe(false);
  });

  test("error state shows retry affordance", async () => {
    mockJson("GET", "/api/srs/due", () => {
      throw new Error("network down");
    }, 500);
    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });
    // Ship 7 voice sweep: generic "Try again" was replaced with
    // concrete recovery actions. Either path here ("Reload the queue"
    // on the error card, "Refresh queue" on a graceful-degrade intro)
    // is a valid recovery affordance.
    expect(
      screen.queryByText(/Reload the queue|Refresh queue/i)
    ).toBeTruthy();
  });
});
