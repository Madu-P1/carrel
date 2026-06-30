import { fireEvent, render } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { QuestionInput } from "./components/QuestionInput";

function renderInput(value: string, onSubmit: () => void) {
  const { container } = render(
    <QuestionInput
      value={value}
      onSubmit={onSubmit}
      onValueChange={() => {}}
    />
  );
  return container.querySelector("form") as HTMLFormElement;
}

test("(a) empty string: submit does not call onSubmit", () => {
  const spy = vi.fn();
  const form = renderInput("", spy);
  fireEvent.submit(form);
  expect(spy).not.toHaveBeenCalled();
});

test("(b) whitespace-only: submit does not call onSubmit", () => {
  const spy = vi.fn();
  const form = renderInput("   ", spy);
  fireEvent.submit(form);
  expect(spy).not.toHaveBeenCalled();
});

test("(c) non-empty trimmed query: submit calls onSubmit exactly once", () => {
  const spy = vi.fn();
  const form = renderInput("What is the holding in this case?", spy);
  fireEvent.submit(form);
  expect(spy).toHaveBeenCalledTimes(1);
});
