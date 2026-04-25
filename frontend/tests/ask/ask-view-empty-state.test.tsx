import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { AskView } from "../../src/features/ask/AskView";

test("AskView empty state seeds a sample question from the primary action", async () => {
  render(<AskView />);

  expect(screen.getByText(/Ask a question about your sources/i)).toBeDefined();

  fireEvent.click(screen.getByRole("button", { name: /Try a sample question/i }));

  const field = screen.getByLabelText(/Question/i) as HTMLInputElement;
  expect(field.value).toBe("What do my sources say about mitosis checkpoints?");
});
