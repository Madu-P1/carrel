import { fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { expect, test } from "vitest";

import { ManageCardsView } from "../../src/features/study/ManageCardsView";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

/**
 * Pin the audit findings on ManageCardsView (P1 + P2):
 *   1. Local list mutations keep `offset` in sync with the visible row
 *      count, so "Load more" doesn't duplicate or skip cards. Covered
 *      by the create + delete tests below — both flows go through the
 *      same `setOffset(...)` invariant.
 *   2. Optimistic prepend is gated on `subject === null`. Orphan cards
 *      from CardCreateDialog don't leak into a subject-filtered list.
 *
 * The endpoint surface tested:
 *   GET  /api/srs/cards     (paginated list — offset is what we pin)
 *   POST /api/srs/cards     (create one orphan card)
 *   DELETE /api/srs/cards/:id
 *   GET  /api/srs/subjects  (chip seed)
 */

const PAGE_SIZE = 50;

interface Card {
  id: string;
  front: string;
  back: string;
  state: string;
  difficulty: number;
  reps: number;
  lapses: number;
  due_date: string | null;
  last_review: string | null;
  card_type: string | null;
  concept_id: string | null;
  concept: string | null;
  document_id: string | null;
  document_name: string | null;
  subject_name: string | null;
}

function makeCard(id: string, subject: string | null = null): Card {
  return {
    id,
    front: `Q ${id}`,
    back: `A ${id}`,
    state: "new",
    difficulty: 0.3,
    reps: 0,
    lapses: 0,
    due_date: null,
    last_review: null,
    card_type: "custom",
    concept_id: null,
    concept: null,
    document_id: null,
    document_name: null,
    subject_name: subject,
  };
}

function makeCards(n: number, subject: string | null = null) {
  return Array.from({ length: n }, (_, i) => makeCard(`c${i}`, subject));
}

interface ListCall {
  offset: number;
  subject: string | undefined;
}

/**
 * Wire the SRS endpoints. `listCalls` records every GET so tests can
 * assert "Load more" used the right offset on its follow-up request.
 */
function installFetch(opts: {
  initialBatch: Card[];
  total: number;
  subjects?: Array<{ subject_name: string; card_count: number; due_count: number }>;
  createdCard?: Card;
}) {
  const listCalls: ListCall[] = [];
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/srs/cards" && init.method === "GET") {
      const offset = Number(url.searchParams.get("offset") ?? 0);
      const subject = url.searchParams.get("subject") ?? undefined;
      listCalls.push({ offset, subject });
      if (offset === 0) {
        return jsonResponse({
          cards: opts.initialBatch,
          total: opts.total,
          limit: PAGE_SIZE,
          offset: 0,
        });
      }
      // Synthetic page for "Load more" — content doesn't matter; the
      // offset we received is what these tests verify.
      return jsonResponse({
        cards: [makeCard(`page-${offset}`)],
        total: opts.total,
        limit: PAGE_SIZE,
        offset,
      });
    }
    if (url.pathname === "/api/srs/cards" && init.method === "POST") {
      return jsonResponse({ card: opts.createdCard ?? makeCard("orphan-new") });
    }
    if (url.pathname.startsWith("/api/srs/cards/") && init.method === "DELETE") {
      return jsonResponse({ deleted: 1 });
    }
    if (url.pathname === "/api/srs/subjects" && init.method === "GET") {
      return jsonResponse({ subjects: opts.subjects ?? [] });
    }
    return undefined;
  });
  return listCalls;
}

test("delete keeps offset in sync — next Load more requests offset = visible count", async () => {
  // 3 visible / 8 total. After deleting one, the next "Load more"
  // request must use offset=2 (one fewer than the original 3), not 3.
  const listCalls = installFetch({
    initialBatch: makeCards(3),
    total: 8,
  });

  render(<ManageCardsView />);

  // Wait for the initial page.
  await screen.findByText("Q c0");

  // Click the row's delete affordance, then Confirm.
  fireEvent.click(screen.getByRole("button", { name: /Delete card: Q c0/i }));
  fireEvent.click(await screen.findByRole("button", { name: /^Confirm$/i }));

  await waitFor(() => {
    expect(screen.queryByText("Q c0")).toBeNull();
  });

  // "Load more" — the URL must show offset=2, the new visible count.
  fireEvent.click(
    await screen.findByRole("button", { name: /^Load \d+ more$/i })
  );

  await waitFor(() => {
    const last = listCalls[listCalls.length - 1];
    expect(last).toBeDefined();
    expect(last.offset).toBe(2);
  });
});

test("create keeps offset in sync — next Load more requests offset = visible count + 1", async () => {
  // 3 visible / 8 total + a successful POST that returns an orphan.
  const listCalls = installFetch({
    initialBatch: makeCards(3),
    total: 8,
    createdCard: {
      ...makeCard("c-new"),
      front: "Brand new front",
      back: "Brand new back",
    },
  });

  render(<ManageCardsView />);
  await screen.findByText("Q c0");

  // Open the New-card dialog and submit a card.
  fireEvent.click(screen.getByRole("button", { name: /^New card$/i }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.input(within(dialog).getByLabelText(/^Front/i), {
    currentTarget: { value: "Brand new front" },
    target: { value: "Brand new front" },
  });
  fireEvent.input(within(dialog).getByLabelText(/^Back/i), {
    currentTarget: { value: "Brand new back" },
    target: { value: "Brand new back" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: /^Create card$/i }));

  // The prepended card lands in the visible list.
  await screen.findByText("Brand new front");

  // "Load more" — offset must be 4 (3 initial + 1 new), not 3.
  fireEvent.click(
    await screen.findByRole("button", { name: /^Load \d+ more$/i })
  );

  await waitFor(() => {
    const last = listCalls[listCalls.length - 1];
    expect(last).toBeDefined();
    expect(last.offset).toBe(4);
  });
});

test("orphan card from CardCreateDialog is NOT prepended when a subject filter is active", async () => {
  // 3 cards in subject "Math" out of 8 total. After clicking Math, the
  // user is filtered. Creating an orphan must NOT show in the list (the
  // orphan goes under "All subjects"); the toast acknowledges the save
  // and the user is directed to where the card actually lives.
  const listCalls = installFetch({
    initialBatch: makeCards(3, "Math"),
    total: 8,
    subjects: [
      { subject_name: "Math", card_count: 3, due_count: 0 },
      { subject_name: "Bio", card_count: 2, due_count: 0 },
    ],
    createdCard: {
      ...makeCard("orphan-1"),
      front: "Should not appear in Math view",
      back: "Hidden answer",
    },
  });

  render(<ManageCardsView />);

  // Wait for the chips, then activate the Math filter. The Math chip
  // is a button with the subject name as its accessible name.
  fireEvent.click(await screen.findByRole("button", { name: /^Math/i }));

  // Wait for the filtered list to land.
  await waitFor(() => {
    const last = listCalls[listCalls.length - 1];
    expect(last?.subject).toBe("Math");
  });
  await screen.findByText("Q c0");

  // Open the New-card dialog and create an orphan.
  fireEvent.click(screen.getByRole("button", { name: /^New card$/i }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.input(within(dialog).getByLabelText(/^Front/i), {
    currentTarget: { value: "Should not appear in Math view" },
    target: { value: "Should not appear in Math view" },
  });
  fireEvent.input(within(dialog).getByLabelText(/^Back/i), {
    currentTarget: { value: "Hidden answer" },
    target: { value: "Hidden answer" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: /^Create card$/i }));

  // Settle on the post-create state. The orphan front text MUST NOT be
  // in the visible list — the filter contract holds.
  await waitFor(() => {
    expect(
      screen.queryByText("Should not appear in Math view")
    ).toBeNull();
  });
});
