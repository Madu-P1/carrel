import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Stack } from "./Stack";

test("Stack renders children in order", () => {
  render(
    <Stack>
      <span>First</span>
      <span>Second</span>
    </Stack>
  );

  expect(screen.getAllByText(/First|Second/).map((node) => node.textContent)).toEqual([
    "First",
    "Second"
  ]);
});

test("Stack supports horizontal layouts", () => {
  const { container } = render(
    <Stack direction="horizontal">
      <span>Item</span>
    </Stack>
  );

  expect(container.firstElementChild).toBeTruthy();
});
