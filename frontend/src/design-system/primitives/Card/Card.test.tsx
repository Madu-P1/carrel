import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Card } from "./Card";

test("Card renders section content", () => {
  render(<Card>Summary</Card>);

  expect(screen.getByText("Summary")).toBeDefined();
});

test("Card supports padding variants", () => {
  const { container } = render(<Card padding="lg">Large</Card>);

  expect(container.querySelector("section")).toBeTruthy();
});
