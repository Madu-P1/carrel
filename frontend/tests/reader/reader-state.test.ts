import { expect, test } from "vitest";

import {
  persistReaderRestorationState,
  readerState,
  readReaderRestorationState,
  requestReaderFind,
  requestReaderPage,
  restoreReaderState,
  setReaderCurrentPage
} from "../../src/features/reader/state";


test("requestReaderPage and current page updates are clamped to total pages", () => {
  readerState.totalPages.value = 5;

  requestReaderPage(99);
  setReaderCurrentPage(0);

  expect(readerState.requestedPage.value).toBe(5);
  expect(readerState.currentPage.value).toBe(1);
});

test("reader find requests expose a serial API for menu and keyboard commands", () => {
  const before = readerState.findRequestSerial.value;

  requestReaderFind();

  expect(readerState.findRequestSerial.value).toBe(before + 1);
});

test("reader restoration state persists only layout-safe reading metadata", () => {
  readerState.currentPage.value = 4;
  readerState.scale.value = 1.35;
  readerState.fitMode.value = "custom";
  readerState.outlineOpen.value = false;

  persistReaderRestorationState("doc 1", {
    page: 4,
    scrollTop: 1234
  });

  const restored = readReaderRestorationState("doc 1");
  expect(restored).toMatchObject({
    fitMode: "custom",
    outlineOpen: false,
    page: 4,
    scale: 1.35,
    scrollTop: 1234
  });
  expect(Object.keys(restored ?? {})).toEqual([
    "fitMode",
    "outlineOpen",
    "page",
    "scale",
    "scrollTop",
    "updatedAt"
  ]);
});

test("restoreReaderState reapplies page, fit, scale, and outline state", () => {
  restoreReaderState({
    fitMode: "fit-page",
    outlineOpen: false,
    page: 3,
    scale: 1.2,
    scrollTop: 900,
    updatedAt: "2026-05-02T00:00:00.000Z"
  });

  expect(readerState.currentPage.value).toBe(3);
  expect(readerState.requestedPage.value).toBe(3);
  expect(readerState.fitMode.value).toBe("fit-page");
  expect(readerState.scale.value).toBe(1.2);
  expect(readerState.outlineOpen.value).toBe(false);
});
