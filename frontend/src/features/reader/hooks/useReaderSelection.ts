import type { RefObject } from "preact";
import { useEffect } from "preact/hooks";

import { readerState } from "../state";

export function useReaderSelection(containerRef: RefObject<HTMLElement>): void {
  useEffect(() => {
    const updateSelection = () => {
      const container = containerRef.current;
      const selection = window.getSelection();
      if (!container || !selection || selection.rangeCount === 0) {
        readerState.selectedText.value = "";
        return;
      }

      const text = selection.toString().trim();
      const anchor = selection.anchorNode;
      if (!text || !anchor || !container.contains(anchor)) {
        readerState.selectedText.value = "";
        return;
      }

      readerState.selectedText.value = text;
    };

    document.addEventListener("selectionchange", updateSelection);
    return () => {
      document.removeEventListener("selectionchange", updateSelection);
    };
  }, [containerRef]);
}
