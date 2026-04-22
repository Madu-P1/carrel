import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Divider } from "./Divider";

test("Divider renders a separator", () => {
  render(<Divider />);

  expect(screen.getByRole("separator")).toBeDefined();
});

test("Divider supports vertical orientation", () => {
  render(<Divider orientation="vertical" />);

  expect(screen.getByRole("separator").getAttribute("aria-orientation")).toBe(
    "vertical"
  );
});
