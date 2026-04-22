import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { ScrollArea } from "./ScrollArea";

test("ScrollArea renders content", () => {
  render(<ScrollArea>Scrollable</ScrollArea>);

  expect(screen.getByText("Scrollable")).toBeDefined();
});

test("ScrollArea accepts sizing styles", () => {
  const { container } = render(
    <ScrollArea style={{ maxHeight: "40px" }}>Sized</ScrollArea>
  );

  expect(container.firstElementChild?.getAttribute("style")).toContain("max-height");
});
