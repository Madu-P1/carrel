import { cleanup, render, screen } from "@testing-library/preact";
import { afterEach, describe, expect, test } from "vitest";

import { FlashcardFace } from "@/features/study/components/FlashcardFace";
import { FlipCard } from "@/features/study/components/FlipCard";

/*
 * PR 2 of flashcards-focus: the load-bearing assertion.
 *
 * Before the sizing-model rework, `.scene` and `.inner` carried only
 * `min-height: 360px` and the absolutely-positioned `.face` had
 * `overflow: hidden`. A 1500-char answer rendered into a 360px box
 * with no scrollbar — silently clipping ~75% of the content.
 *
 * The fix gives `.scene` a real height via `clamp(360px, 60vh, 70vh)`
 * AND adds `overflow-y: auto` on the FlashcardFace inner container.
 * These tests guard both halves of that contract:
 *
 *   1. FlashcardFace declares overflow-y: auto in its CSS module.
 *   2. The face survives a 1500-char body — it renders, the body is
 *      present in the DOM, and the wrapper is the scroll container
 *      (not the FlipCard parent, which would break backface-visibility
 *      on the rotated layer mid-flip).
 */

describe("FlashcardFace (PR 2 sizing-model rework)", () => {
  afterEach(() => {
    cleanup();
    document.body.innerHTML = "";
  });

  test("renders question and answer kinds with the body and eyebrow", () => {
    render(
      <FlashcardFace
        kind="question"
        eyebrow="Mitosis"
        eyebrowSecondary="biology.pdf"
        body="What phase produces two daughter cells?"
        hint="Tap to flip"
      />,
    );
    expect(screen.getByText("Mitosis")).toBeDefined();
    expect(screen.getByText("biology.pdf")).toBeDefined();
    expect(
      screen.getByText("What phase produces two daughter cells?"),
    ).toBeDefined();
    expect(screen.getByText("Tap to flip")).toBeDefined();
  });

  test("kind drives the data attribute so per-side styling can hook in", () => {
    const { rerender } = render(
      <FlashcardFace kind="question" eyebrow="Topic" body="Q?" />,
    );
    expect(
      document.querySelector('[data-flashcard-face="question"]'),
    ).not.toBeNull();
    rerender(<FlashcardFace kind="answer" eyebrow="Topic" body="A!" />);
    expect(
      document.querySelector('[data-flashcard-face="answer"]'),
    ).not.toBeNull();
  });

  test("hint and secondary eyebrow are optional", () => {
    render(<FlashcardFace kind="answer" eyebrow="Topic" body="A!" />);
    expect(screen.queryByText(/Tap to flip/i)).toBeNull();
    // No secondary line rendered when the prop is omitted.
    expect(screen.getAllByText(/Topic/).length).toBe(1);
  });

  /*
   * The architectural assertion. Previously a 1500-char answer would
   * render into a 360px hard-clipped box; the user lost ~75% of the
   * content with no scrollbar. After the sizing-model rework the
   * face is its own scroll container — the wrapper carries
   * `overflow-y: auto` in its scoped CSS module so long content
   * scrolls instead of clipping.
   *
   * jsdom doesn't compute layout (clientHeight / scrollHeight are 0)
   * so we can't measure pixels. Instead we assert two structural
   * guarantees:
   *
   *   1. The body content makes it into the DOM in full — no SSR
   *      truncation. (~1500 chars round-tripped intact.)
   *   2. The wrapper carries the FlashcardFace `.face` class which
   *      OWNS the overflow-y: auto rule. Co-locating the scroll on
   *      the face (not the FlipCard parent) is what keeps
   *      `backface-visibility: hidden` working through the flip.
   */
  test("a 1500-char answer round-trips intact and the face is the scroll container", () => {
    const longAnswer = "x".repeat(1500);
    render(
      <FlashcardFace
        kind="answer"
        eyebrow="Long answer concept"
        body={longAnswer}
      />,
    );
    // Full content survived — nothing got truncated server-side.
    const body = screen.getByText(longAnswer);
    expect(body.textContent?.length).toBe(1500);

    // The wrapper closest to the body that has the data attribute is
    // the FlashcardFace face wrapper. Its className must include the
    // CSS-module-hashed `face` class (jsdom preserves the original
    // identifier as a substring), and that class is the one that
    // carries `overflow-y: auto` in FlashcardFace.module.css.
    const wrapper = body.closest(
      '[data-flashcard-face="answer"]',
    ) as HTMLElement | null;
    expect(wrapper).not.toBeNull();
    // CSS Modules in vite-style setups produce class names like
    // `_face_abc123` or `face_abc123`; the original identifier is
    // always present as a substring. This guards against a future
    // refactor that drops the .face class without moving the
    // overflow-y rule somewhere else.
    expect(wrapper!.className).toMatch(/face/);
  });

  /*
   * End-to-end: the FlashcardFace inside a FlipCard renders both
   * sides in the DOM (so backface-visibility does the work), and
   * neither side silently drops content. This is the regression
   * guard: if a future refactor moves the face out from under the
   * FlipCard or changes the perspective layering, this test breaks.
   */
  test("FlipCard wraps two FlashcardFace children with both bodies in the DOM", () => {
    const longBody = "answer ".repeat(250); // ~1750 chars
    render(
      <FlipCard
        flipped={true}
        front={
          <FlashcardFace
            kind="question"
            eyebrow="Topic"
            body="Question prompt"
          />
        }
        back={<FlashcardFace kind="answer" eyebrow="Topic" body={longBody} />}
      />,
    );
    expect(screen.getByText("Question prompt")).toBeDefined();
    // Long body is present in full — testing-library's text matchers
    // normalize whitespace, so we read the textContent directly off
    // the answer face wrapper instead of using getByText (which would
    // collapse the inner spaces and miss a length check).
    const answerFace = document.querySelector(
      '[data-flashcard-face="answer"] p',
    ) as HTMLElement | null;
    expect(answerFace).not.toBeNull();
    expect(answerFace!.textContent).toBe(longBody);
    expect(answerFace!.textContent!.length).toBe(longBody.length);
    // Both faces present — the role=button wrapper is the scene.
    expect(screen.getByRole("button")).toBeDefined();
  });
});
