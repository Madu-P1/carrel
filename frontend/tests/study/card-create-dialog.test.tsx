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

test("CardCreateDialog exposes three card kinds: Q&A, Cloze, Reverse pair", () => {
  render(
    <CardCreateDialog activeSubject={null} onClose={() => {}} onCreated={() => {}} open />
  );
  expect(screen.getByRole("button", { name: /Q & A/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /^Cloze$/ })).toBeDefined();
  expect(screen.getByRole("button", { name: /Reverse pair/ })).toBeDefined();
});

test("CardCreateDialog reverse-pair mode posts to /pair and calls onCreated twice", async () => {
  let captured: unknown = null;
  let calls = 0;
  registerFetchHandler((url, init) => {
    if (!url.pathname.endsWith("/api/srs/cards/pair") || init.method !== "POST") {
      return undefined;
    }
    calls += 1;
    captured = init.body ? JSON.parse(init.body as string) : null;
    return jsonResponse({
      primary: {
        id: "card-primary",
        front: "Femur",
        back: "The thigh bone",
        state: "new",
        difficulty: 0.3,
        reps: 0,
        lapses: 0,
        due_date: "2026-05-13",
        last_review: null,
        card_type: "custom",
        kind: "qa",
        concept_id: null,
        concept: null,
        document_id: null,
        document_name: null,
        subject_name: null,
      },
      reverse: {
        id: "card-reverse",
        front: "The thigh bone",
        back: "Femur",
        state: "new",
        difficulty: 0.3,
        reps: 0,
        lapses: 0,
        due_date: "2026-05-13",
        last_review: null,
        card_type: "custom",
        kind: "reverse",
        concept_id: null,
        concept: null,
        document_id: null,
        document_name: null,
        subject_name: null,
      },
      primary_id: "card-primary",
      reverse_id: "card-reverse",
    });
  });

  const onCreated = vi.fn();
  const onClose = vi.fn();
  render(
    <CardCreateDialog activeSubject={null} onClose={onClose} onCreated={onCreated} open />
  );

  // Switch to Reverse pair mode.
  fireEvent.click(screen.getByRole("button", { name: /Reverse pair/ }));

  // Labels swap to Term / Definition.
  const termBox = screen.getByLabelText(/^Term/i);
  const definitionBox = screen.getByLabelText(/^Definition/i);
  fireEvent.input(termBox, { target: { value: "Femur" } });
  fireEvent.input(definitionBox, { target: { value: "The thigh bone" } });

  // Submit button text adapts to "Create pair".
  const submitBtn = screen.getByRole("button", { name: /Create pair/ });
  expect(submitBtn).toHaveProperty("disabled", false);
  fireEvent.click(submitBtn);

  await waitFor(() => expect(onCreated).toHaveBeenCalledTimes(2));
  expect(onClose).toHaveBeenCalledTimes(1);
  expect(calls).toBe(1);
  expect(captured).toMatchObject({
    front: "Femur",
    back: "The thigh bone",
    concept_id: null,
    card_type: "custom",
  });
});
