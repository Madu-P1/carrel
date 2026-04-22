import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { Input } from "./Input";

test("Input renders label and helper text", () => {
  render(<Input helpText="Helpful" label="Question" />);

  expect(screen.getByText("Question")).toBeDefined();
  expect(screen.getByText("Helpful")).toBeDefined();
});

test("Input emits input events", () => {
  const onInput = vi.fn();
  render(<Input onInput={onInput} label="Name" />);

  fireEvent.input(screen.getByRole("textbox"), {
    target: { value: "Einstein" }
  });

  expect(onInput).toHaveBeenCalled();
});

test("Input marks invalid state when error exists", () => {
  render(<Input error="Required" label="Source" />);

  expect(screen.getByRole("textbox").getAttribute("aria-invalid")).toBe("true");
});
