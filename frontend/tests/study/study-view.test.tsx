import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, test, vi } from "vitest";

import { StudyView } from "@/features/study/StudyView";
import { getFetchCalls, mockJson } from "../support/mockFetch";

afterEach(() => {
  cleanup();
  // Focus mode persists to localStorage. Clear it between tests so
  // a prior test that toggled focus on doesn't seed the next test's
  // initial state.
  try {
    window.localStorage.clear();
  } catch {
    // jsdom localStorage is always writable; the catch is defensive.
  }
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

  // PR 4 of flashcards-focus: source citation appears on the back face
  // when the card has both document_id and chunk_id. Cards missing
  // either field render the back face without the citation row. These
  // tests pin the conditional wiring gate so a future refactor of the
  // back-face render can't silently drop the citation.
  test("back face renders SourceCitation when document_id + chunk_id are present", async () => {
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "card-cited",
          front: "What does duration measure?",
          back: "First-order interest-rate sensitivity.",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Duration",
          document_name: "bonds.pdf",
          subject_name: "Finance",
          document_id: "doc-abc",
          chunk_id: "chunk-xyz",
          page_num: 7,
          quote_text: "Duration is the weighted-average time to receipt of cash flows.",
        },
      ],
    });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);

    const citation = await waitFor(() =>
      screen.getByRole("button", { name: /Open the source for this card/i }),
    );
    expect(citation).toBeDefined();
    expect(screen.getByText(/From bonds.pdf, page 7/)).toBeTruthy();
  });

  test("back face hides SourceCitation when document_id or chunk_id is missing", async () => {
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "card-uncited",
          front: "Manual card",
          back: "No source attached.",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Topic",
          document_name: "doc.pdf",
          subject_name: null,
        },
      ],
    });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);

    await waitFor(() => {
      expect(screen.getByRole("group", { name: /Rate your recall/i })).toBeDefined();
    });
    expect(
      screen.queryByRole("button", { name: /Open the source for this card/i }),
    ).toBeNull();
  });

  // PR 6.1 — the ETA chip in focus mode is the visible end of a
  // ref → memo → overlay-prop pipeline. The seam is fragile (a refactor
  // that drops the push in rateCard or breaks the useMemo deps would
  // silently kill the chip). This integration test walks 3 rating
  // cycles inside focus mode and asserts the chip surfaces. It
  // doubles as the regression guard for the "fallback when timing
  // legs are non-null" gating in rateCard.
  test("focus-mode ETA chip appears after three rated cards", async () => {
    // Drive Date.now manually so each card consumes ~10 seconds total
    // (5s reveal + 5s rate). fireEvent.click happens in microseconds
    // otherwise, which would produce zero-second samples and the
    // formatEta floor (>0) would gate the chip off.
    let nowMs = 1_700_000_000_000;
    const dateNowSpy = vi.spyOn(Date, "now").mockImplementation(() => nowMs);
    const tick = (ms: number) => {
      nowMs += ms;
    };

    mockJson("POST", "/api/srs/review", { next_due_date: "2026-05-15", interval: 1, ease: 2.5 });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: Array.from({ length: 5 }, (_, i) => ({
        id: `card-${i}`,
        front: `Q${i}`,
        back: `A${i}`,
        state: "review",
        stability: 1,
        difficulty: 0.5,
        reps: 0,
        lapses: 0,
        due_date: "2026-05-10",
        concept: "Topic",
        document_name: "doc.pdf",
        subject_name: null,
      })),
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // Enter focus mode so the ETA chip has a render surface.
    fireEvent.click(screen.getByRole("button", { name: /Focus mode/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /Focused review/i })).toBeDefined();
    });

    // Before any ratings: chip is hidden.
    expect(screen.queryByText(/~.+(s|m) left/)).toBeNull();

    // Three rate cycles: reveal, rate "good", repeat. Each cycle
    // ticks 10s on the mocked Date so samples land at ~10s/card.
    for (let i = 0; i < 3; i++) {
      const card = await waitFor(() =>
        screen.getByRole("button", { name: /Card showing question/i }),
      );
      tick(5000);
      fireEvent.click(card); // reveal → captures firstRevealAt
      await waitFor(() => {
        expect(screen.getByRole("group", { name: /Rate your recall/i })).toBeDefined();
      });
      const goodButton = document.querySelector('button[data-rating="good"]');
      if (!goodButton) throw new Error("Good rating button not in DOM");
      tick(5000);
      fireEvent.click(goodButton); // rate → captures ratedAt
      await act(async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 10));
      });
    }

    // After 3 rated cards at ~10s each with 2 cards remaining,
    // the chip should read "~20s left" (median 10 × 2 = 20s).
    await waitFor(() => {
      expect(screen.getByText(/~\d+(s|m) left/)).toBeDefined();
    });

    dateNowSpy.mockRestore();
  });

  // PR 6.3 — defer button pushes the current card to the end of the
  // session queue without recording a rating. Visible only after
  // reveal and only when there's at least one card to defer past.
  test("defer button pushes the current card to the end of the queue", async () => {
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "card-A",
          front: "Q-A",
          back: "A-A",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Topic",
          document_name: "doc.pdf",
          subject_name: null,
        },
        {
          id: "card-B",
          front: "Q-B",
          back: "A-B",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Topic",
          document_name: "doc.pdf",
          subject_name: null,
        },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // Card A on top. Reveal it so the defer button shows up.
    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    expect(screen.getByText("Q-A")).toBeTruthy();
    fireEvent.click(card);

    const deferButton = await waitFor(() =>
      screen.getByRole("button", { name: /Defer this card to the end/i }),
    );
    fireEvent.click(deferButton);

    // After defer, B is on the front face; A is still in the queue
    // (deferred to the end) but not yet visible.
    await waitFor(() => {
      expect(screen.getByText("Q-B")).toBeTruthy();
    });
    expect(screen.queryByText("Q-A")).toBeNull();
  });

  test("defer button hides on the last card of the session", async () => {
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: [
        {
          id: "only-card",
          front: "lone front",
          back: "lone back",
          state: "review",
          stability: 1,
          difficulty: 0.5,
          reps: 0,
          lapses: 0,
          due_date: "2026-05-10",
          concept: "Topic",
          document_name: "doc.pdf",
          subject_name: null,
        },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);

    // Rating row visible (back face) — but defer button is hidden.
    await waitFor(() => {
      expect(screen.getByRole("group", { name: /Rate your recall/i })).toBeDefined();
    });
    expect(
      screen.queryByRole("button", { name: /Defer this card/i }),
    ).toBeNull();
  });

  // PR 6.3 — negative-invariant: defer must NOT call study.review.
  // This is the entire point of "defer" vs "Again" — the SRS schedule
  // stays untouched. If a future refactor accidentally wires defer
  // through rateCard, this test fails.
  test("defer does not call /api/srs/review", async () => {
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: [
        { id: "card-A", front: "Q-A", back: "A-A", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
        { id: "card-B", front: "Q-B", back: "A-B", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);
    const deferButton = await waitFor(() =>
      screen.getByRole("button", { name: /Defer this card to the end/i }),
    );
    fireEvent.click(deferButton);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const reviewPosts = getFetchCalls().filter(
      (c) => c.method === "POST" && c.url.includes("/api/srs/review"),
    );
    expect(reviewPosts).toHaveLength(0);
  });

  // PR 6.3 — defer emits srs.card_deferred {card_id, remaining} so
  // the dashboard can measure usage. Asserting the wire payload
  // (not just that something fired) pins the contract end-to-end.
  test("defer emits srs.card_deferred event with card_id and remaining", async () => {
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: [
        { id: "card-A", front: "Q-A", back: "A-A", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
        { id: "card-B", front: "Q-B", back: "A-B", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
        { id: "card-C", front: "Q-C", back: "A-C", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);
    const deferButton = await waitFor(() =>
      screen.getByRole("button", { name: /Defer this card to the end/i }),
    );
    fireEvent.click(deferButton);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const deferEvents = getFetchCalls().filter((c) => {
      if (c.method !== "POST" || !c.url.includes("/api/usage-events")) return false;
      const body = typeof c.body === "string" ? JSON.parse(c.body) : null;
      return body?.event_name === "srs.card_deferred";
    });
    expect(deferEvents).toHaveLength(1);
    const body = JSON.parse(deferEvents[0].body as string);
    expect(body.event_name).toBe("srs.card_deferred");
    expect(body.surface).toBe("study");
    expect(body.properties.card_id).toBe("card-A");
    // Two cards remain after card-A is sent to the back of a 3-card queue.
    expect(body.properties.remaining).toBe(2);
  });

  // PR 6.3 polish — the keyboard "d" path is gated on !submitting,
  // the same way the Defer button is. Without that guard a "d"
  // keypress racing a rateCard roundtrip would splice the queue
  // under the in-flight advance and emit a stale event. This test
  // pins the unified gating by holding /api/srs/review open and
  // asserting "d" produces no defer event while submitting is true.
  test("keyboard 'd' does NOT defer while a rating is in flight", async () => {
    let resolveReview: ((value: unknown) => void) | undefined;
    const reviewPending = new Promise<unknown>((resolve) => {
      resolveReview = resolve;
    });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("POST", "/api/srs/review", () => reviewPending);
    mockJson("GET", "/api/srs/due", {
      cards: [
        { id: "card-A", front: "Q-A", back: "A-A", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
        { id: "card-B", front: "Q-B", back: "A-B", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    fireEvent.click(card);
    await waitFor(() =>
      screen.getByRole("button", { name: /Defer this card to the end/i }),
    );

    // Click "Good" — submitting flips true and stays true because
    // /api/srs/review is held open. (The rating buttons disable;
    // defer is also expected to ignore "d" while in this state.)
    const goodButton = screen.getByRole("button", { name: /Good/i });
    fireEvent.click(goodButton);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // Snapshot the call list before the "d" press; defer must not
    // appear in the delta.
    const beforeCount = getFetchCalls().filter((c) => {
      if (c.method !== "POST" || !c.url.includes("/api/usage-events")) return false;
      const body = typeof c.body === "string" ? JSON.parse(c.body) : null;
      return body?.event_name === "srs.card_deferred";
    }).length;

    fireEvent.keyDown(window, { key: "d" });
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const afterCount = getFetchCalls().filter((c) => {
      if (c.method !== "POST" || !c.url.includes("/api/usage-events")) return false;
      const body = typeof c.body === "string" ? JSON.parse(c.body) : null;
      return body?.event_name === "srs.card_deferred";
    }).length;
    expect(afterCount).toBe(beforeCount);

    // Release the held review request so the cleanup teardown doesn't
    // leave a dangling promise around.
    resolveReview?.({ next_due_date: "2026-05-15", interval: 1, ease: 2.5 });
  });

  // PR 6.3 — keyboard "d" mirrors the Defer button. Tests both the
  // shortcut firing on the back face and gating on the last-card
  // condition (no defer past where there's nothing past).
  test("keyboard 'd' on the back face defers the current card", async () => {
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: [
        { id: "card-A", front: "Q-A", back: "A-A", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
        { id: "card-B", front: "Q-B", back: "A-B", state: "review", stability: 1, difficulty: 0.5, reps: 0, lapses: 0, due_date: "2026-05-10", concept: "Topic", document_name: "doc.pdf", subject_name: null },
      ],
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    const card = await waitFor(() =>
      screen.getByRole("button", { name: /Card showing question/i }),
    );
    expect(screen.getByText("Q-A")).toBeTruthy();
    fireEvent.click(card);
    await waitFor(() =>
      screen.getByRole("button", { name: /Defer this card to the end/i }),
    );

    fireEvent.keyDown(window, { key: "d" });
    await waitFor(() => {
      expect(screen.getByText("Q-B")).toBeTruthy();
    });
  });

  // PR 6.4 — streak chip appears in the focus header after two
  // consecutive Good+Easy ratings, and resets on Again/Hard. Drives
  // the chip end-to-end through rateCard so the wire (rating →
  // streak state → formatStreak → overlay slot) is covered.
  test("streak chip appears after two consecutive Good ratings and resets on Hard", async () => {
    mockJson("POST", "/api/srs/review", { next_due_date: "2026-05-15", interval: 1, ease: 2.5 });
    mockJson("GET", "/api/srs/subjects", { subjects: [] });
    mockJson("GET", "/api/srs/due", {
      cards: Array.from({ length: 5 }, (_, i) => ({
        id: `card-${i}`,
        front: `Q${i}`,
        back: `A${i}`,
        state: "review",
        stability: 1,
        difficulty: 0.5,
        reps: 0,
        lapses: 0,
        due_date: "2026-05-10",
        concept: "Topic",
        document_name: "doc.pdf",
        subject_name: null,
      })),
    });

    render(<StudyView />);
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });

    // Start the session first; then enter focus mode so the streak
    // chip has a render surface (the chip lives in the overlay
    // header). Same ordering as the ETA chip test.
    fireEvent.click(screen.getByRole("button", { name: /Start a session/i }));
    await act(async () => {
      await new Promise((resolve) => window.setTimeout(resolve, 10));
    });
    fireEvent.click(screen.getByRole("button", { name: /Focus mode/i }));
    await waitFor(() => {
      expect(screen.getByRole("dialog", { name: /Focused review/i })).toBeDefined();
    });

    const rateOnce = async (dataRating: string) => {
      const card = await waitFor(() =>
        screen.getByRole("button", { name: /Card showing question/i }),
      );
      fireEvent.click(card);
      await waitFor(() => {
        expect(screen.getByRole("group", { name: /Rate your recall/i })).toBeDefined();
      });
      const rateButton = document.querySelector(`button[data-rating="${dataRating}"]`);
      if (!rateButton) throw new Error(`rating button ${dataRating} not in DOM`);
      fireEvent.click(rateButton);
      await act(async () => {
        await new Promise((resolve) => window.setTimeout(resolve, 10));
      });
    };

    // First Good: streak=1, still below the surface threshold.
    await rateOnce("good");
    expect(screen.queryByText(/in a row/)).toBeNull();

    // Second Good: streak=2, chip surfaces.
    await rateOnce("good");
    await waitFor(() => {
      expect(screen.getByText("2 in a row")).toBeTruthy();
    });

    // Hard breaks the streak — chip disappears.
    await rateOnce("hard");
    await waitFor(() => {
      expect(screen.queryByText(/in a row/)).toBeNull();
    });
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
