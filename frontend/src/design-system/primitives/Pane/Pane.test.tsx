import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Pane } from "./Pane";

test("Pane renders its content", () => {
  render(<Pane title="Reader">Content</Pane>);

  expect(screen.getByText("Content")).toBeDefined();
});

test("Pane toggles collapsed state", () => {
  render(<Pane title="Reader">Content</Pane>);

  const button = screen.getByRole("button");
  expect(button.getAttribute("aria-expanded")).toBe("true");
  fireEvent.click(button);
  expect(button.getAttribute("aria-expanded")).toBe("false");
});
