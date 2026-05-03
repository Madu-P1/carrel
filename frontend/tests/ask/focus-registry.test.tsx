import { render } from "@testing-library/preact";
import { expect, test } from "vitest";

import { focusAskInput } from "../../src/features/ask/focusRegistry";

test("focusAskInput uses the stable focus target instead of placeholder copy", () => {
  render(
    <input
      aria-label="Question"
      data-focus-target="ask-question"
      placeholder="Renamed copy is safe"
    />
  );

  expect(focusAskInput()).toBe(true);
  expect(document.activeElement?.getAttribute("data-focus-target")).toBe("ask-question");
});
