import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Icon } from "./Icon";

test("Icon renders an svg", () => {
  const { container } = render(<Icon name="search" />);

  expect(container.querySelector("svg")).toBeTruthy();
});

test("Icon renders a title when provided", () => {
  render(<Icon name="sparkle" title="Sparkle" />);

  expect(screen.getByText("Sparkle")).toBeDefined();
});
