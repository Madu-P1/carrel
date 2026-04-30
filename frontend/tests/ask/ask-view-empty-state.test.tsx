import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { AskView } from "../../src/features/ask/AskView";

test("AskView empty state seeds a sample question from the primary action", async () => {
  render(<AskView />);

  expect(screen.getByText(/Ask a question about your sources/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Try a sample question/i }));

  const field = screen.getByLabelText(/Question/i) as HTMLInputElement;
  // Updated 2026-04-30: ASK_EMPTY_SAMPLE was changed from a
  // biology-specific question to a subject-agnostic one in commit
  // 66a7827a. The test asserts on the new value.
  expect(field.value).toBe("Summarise the main argument across my sources.");
});
