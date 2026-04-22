import { useEffect, useState } from "preact/hooks";
import type { RefObject } from "preact";

import { readerState } from "../state";

interface UsePageVirtualizerOptions {
  containerRef: RefObject<HTMLElement>;
  overscan?: number;
  pageCount: number;
  pageHeight: number;
}

interface PageVirtualizerState {
  totalHeight: number;
  visiblePages: number[];
}

function buildRange(start: number, end: number): number[] {
  const items: number[] = [];
  for (let pageNumber = start; pageNumber <= end; pageNumber += 1) {
    items.push(pageNumber);
  }
  return items;
}

export function usePageVirtualizer({
  containerRef,
  overscan = 1,
  pageCount,
  pageHeight
}: UsePageVirtualizerOptions): PageVirtualizerState {
  const [visiblePages, setVisiblePages] = useState<number[]>([]);

  useEffect(() => {
    const container = containerRef.current;
    if (!container || pageCount <= 0 || pageHeight <= 0) {
      setVisiblePages([]);
      return;
    }

    const update = () => {
      const topIndex = Math.max(Math.floor(container.scrollTop / pageHeight) - overscan, 0);
      const visibleCount = Math.max(Math.ceil(container.clientHeight / pageHeight), 1);
      const endIndex = Math.min(pageCount - 1, topIndex + visibleCount + overscan * 2);
      setVisiblePages(buildRange(topIndex + 1, endIndex + 1));
      readerState.currentPage.value = Math.min(pageCount, Math.floor(container.scrollTop / pageHeight) + 1);
    };

    update();
    container.addEventListener("scroll", update, { passive: true });

    let observer: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined") {
      observer = new ResizeObserver(() => update());
      observer.observe(container);
    } else {
      window.addEventListener("resize", update);
    }

    return () => {
      container.removeEventListener("scroll", update);
      if (observer) {
        observer.disconnect();
      } else {
        window.removeEventListener("resize", update);
      }
    };
  }, [containerRef, overscan, pageCount, pageHeight]);

  return {
    totalHeight: pageCount * pageHeight,
    visiblePages
  };
}
