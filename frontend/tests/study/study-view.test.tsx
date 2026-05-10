import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
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

  // PR 1 of flashcards-focus: bidirectional flip. Prior behavior nulled
  // `onFlip` after reveal so users could not flip back to re-read the
  // question. This regression test asserts that clicking the card a
  // second time returns it to the question face. The contract: flip
  // toggles in BOTH directions; rating remains gated on `phase==="back"`.
  test("clicking card after reveal flips back to the question (bidirectional)", async () => {
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "card-flip",
          front: "Q-side",
          back: "A-side",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Topic",
          document_name: "doc.pdf",
          subject_name: null
        }
      ]
    });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // Start the session — moves into phase=front.
    const startButton = screen.getByRole("button", { name: /Start a session/i });
    fireEvent.click(startButton);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // The FlipCard exposes role=button + aria-pressed reflecting the
    // flipped state. Find the card by its accessible label which the
    // FlipCard primitive sets to "Card showing question..." on front.
    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    expect(card.getAttribute("aria-pressed")).toBe("false");

    // Click 1: front → back (reveal). aria-pressed flips to true and
    // the rating row should appear.
    fireEvent.click(card);
    await waitFor(() => {
      expect(screen.getByRole("group", { name: /Rate your recall/i })).toBeDefined();
    });
    expect(card.getAttribute("aria-pressed")).toBe("true");

    // Click 2 (the bug we are fixing): back → front. The rating row
    // disappears and aria-pressed returns to "false".
    fireEvent.click(card);
    await waitFor(() => {
      expect(screen.queryByRole("group", { name: /Rate your recall/i })).toBeNull();
    });
    expect(card.getAttribute("aria-pressed")).toBe("false");
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
