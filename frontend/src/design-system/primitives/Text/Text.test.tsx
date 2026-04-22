import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Text } from "./Text";

test("Text renders the requested variant", () => {
  render(
    <Text as="h2" variant="h1">
      Heading
    </Text>
  );

  expect(screen.getByText("Heading").tagName).toBe("H2");
});

test("Text supports alternate tones", () => {
  render(<Text tone="secondary">Secondary</Text>);

  expect(screen.getByText("Secondary")).toBeDefined();
});

test("Text keeps display serif variants on regular weight", () => {
  render(
    <Text as="h1" variant="h1" weight="bold">
      Serif heading
    </Text>
  );

  expect(screen.getByText("Serif heading").className).toContain("weight-regular");
});
