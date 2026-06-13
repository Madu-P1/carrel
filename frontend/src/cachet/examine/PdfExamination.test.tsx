import { describe, expect, it } from "vitest";

import { arrowPageDelta } from "./PdfExamination";

// Finding #5: a window-level keydown paged the record on bare and modified
// arrows alike, so Shift+Arrow (extend selection) and arrows whose caret is in
// the selectable text layer flipped the page instead of editing the selection.
// arrowPageDelta is the guard, unit-tested directly because the paging side
// effect is not reliably observable under jsdom (the canvas/text layer is a
// stub there).
function key(init: KeyboardEventInit): KeyboardEvent {
  return new KeyboardEvent("keydown", init);
}

function keyOn(target: Node, init: KeyboardEventInit): KeyboardEvent {
  const event = new KeyboardEvent("keydown", init);
  Object.defineProperty(event, "target", { value: target });
  return event;
}

describe("arrowPageDelta", () => {
  it("pages on a bare Left/Right arrow", () => {
    expect(arrowPageDelta(key({ key: "ArrowRight" }), null)).toBe(1);
    expect(arrowPageDelta(key({ key: "ArrowLeft" }), null)).toBe(-1);
  });

  it("does not page on Shift+Arrow (that is a selection gesture)", () => {
    expect(arrowPageDelta(key({ key: "ArrowRight", shiftKey: true }), null)).toBe(0);
    expect(arrowPageDelta(key({ key: "ArrowLeft", shiftKey: true }), null)).toBe(0);
  });

  it("does not page on a platform modifier + Arrow", () => {
    expect(arrowPageDelta(key({ key: "ArrowRight", metaKey: true }), null)).toBe(0);
    expect(arrowPageDelta(key({ key: "ArrowRight", ctrlKey: true }), null)).toBe(0);
    expect(arrowPageDelta(key({ key: "ArrowRight", altKey: true }), null)).toBe(0);
  });

  it("does not page when defaultPrevented", () => {
    const event = key({ key: "ArrowRight", cancelable: true });
    event.preventDefault();
    expect(arrowPageDelta(event, null)).toBe(0);
  });

  it("leaves an arrow inside the selectable text layer to the caret, but pages outside it", () => {
    const layer = document.createElement("div");
    const span = document.createElement("span");
    layer.appendChild(span);
    document.body.appendChild(layer);

    expect(arrowPageDelta(keyOn(span, { key: "ArrowRight" }), layer)).toBe(0);
    expect(arrowPageDelta(keyOn(document.body, { key: "ArrowRight" }), layer)).toBe(1);

    layer.remove();
  });

  it("never pages on a non-arrow key", () => {
    expect(arrowPageDelta(key({ key: "a" }), null)).toBe(0);
    expect(arrowPageDelta(key({ key: "Enter" }), null)).toBe(0);
    expect(arrowPageDelta(key({ key: " " }), null)).toBe(0);
  });
});
