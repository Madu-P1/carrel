import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { CardCreateDialog } from "../../src/features/study/CardCreateDialog";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

test("CardCreateDialog submits front + back and calls onCreated with the returned card", async () => {
  let captured: unknown = null;
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/srs/cards") || init.method !== "POST") {
      return undefined;
    }
    captured = init.body ? JSON.parse(init.body as string) : null;
    return jsonResponse({
      card: {
        id: "card-new",
        front: "What is liquidity?",
        back: "Ease of converting to cash.",
        state: "new",
        difficulty: 0.3,
        reps: 0,
        lapses: 0,
        due_date: "2026-04-23",
        last_review: null,
        card_type: "custom",
        concept_id: null,
        concept: null,
        document_id: null,
        document_name: null,
        subject_name: null,
      },
    });
  });

  const onCreated = vi.fn();
  const onClose = vi.fn();
  render(
    <CardCreateDialog activeSubject={null} onClose={onClose} onCreated={onCreated} open />
  );

  // Both textareas visible, Create button disabled while fields are empty.
  const frontBox = screen.getByLabelText(/^Front/i);
  const backBox = screen.getByLabelText(/^Back/i);
  const createBtn = screen.getByRole("button", { name: /Create card/i });
  expect(createBtn).toHaveProperty("disabled", true);

  fireEvent.input(frontBox, { target: { value: "What is liquidity?" } });
  fireEvent.input(backBox, { target: { value: "Ease of converting to cash." } });
  expect(createBtn).toHaveProperty("disabled", false);

  fireEvent.click(createBtn);
  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(1));
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(captured).toMatchObject({
    front: "What is liquidity?",
    back: "Ease of converting to cash.",
    concept_id: null,
    card_type: "custom",
  });
});

test("CardCreateDialog surfaces a server error without closing", async () => {
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/srs/cards") || init.method !== "POST") {
      return undefined;
    }
    return jsonResponse({ detail: "server went sideways" }, 500);
  });

  const onCreated = vi.fn();
  const onClose = vi.fn();
  render(
    <CardCreateDialog activeSubject={null} onClose={onClose} onCreated={onCreated} open />
  );

  fireEvent.input(screen.getByLabelText(/^Front/i), { target: { value: "q" } });
  fireEvent.input(screen.getByLabelText(/^Back/i), { target: { value: "a" } });
  fireEvent.click(screen.getByRole("button", { name: /Create card/i }));

  await waitFor(() => {
    // Error message renders via role="alert"; assert on visible text.
    expect(screen.getByRole("alert")).toBeDefined();
  });
  expect(onCreated).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
});

test("CardCreateDialog returns null when closed", () => {
  const { container } = render(
    <CardCreateDialog
      activeSubject={null}
      onClose={() => {}}
      onCreated={() => {}}
      open={false}
    />
  );
  expect(container.querySelector("textarea")).toBeNull();
});
