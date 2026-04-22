import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Box } from "./Box";

test("Box renders children", () => {
  render(<Box>Wrapped</Box>);

  expect(screen.getByText("Wrapped")).toBeDefined();
});

test("Box supports changing the element tag", () => {
  render(<Box as="section">Section box</Box>);

  expect(screen.getByText("Section box").tagName).toBe("SECTION");
});
