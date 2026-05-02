import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { OutlineRail } from "../../src/features/reader/components/OutlineRail";
import { readerState, READER_OUTLINE_WIDTH } from "../../src/features/reader/state";

test("OutlineRail exposes a keyboard-adjustable resize handle", () => {
  readerState.outlineOpen.value = true;

  render(
    <OutlineRail
      outline={[
        {
          children: [],
          pageNumber: 1,
          title: "Chapter outline"
        }
      ]}
    />
  );

  const handle = screen.getByRole("separator", {
    name: /Resize document outline/i
  });

  fireEvent.keyDown(handle, { key: "ArrowRight" });
  expect(readerState.outlineWidth.value).toBe(READER_OUTLINE_WIDTH.default + 16);

  fireEvent.keyDown(handle, { key: "Home" });
  expect(readerState.outlineWidth.value).toBe(READER_OUTLINE_WIDTH.min);
});
