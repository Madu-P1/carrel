import { render, screen } from "@testing-library/preact";
import { expect, test } from "vitest";

import { Markdown } from "./Markdown";

test("Markdown renders a paragraph", () => {
  render(<Markdown source="hello world" />);
  expect(screen.getByText("hello world")).toBeDefined();
});

test("Markdown renders h1 + h2 with correct text", () => {
  const { container } = render(<Markdown source={"# title\n\n## subtitle"} />);
  expect(container.querySelector("h1")?.textContent).toBe("title");
  expect(container.querySelector("h2")?.textContent).toBe("subtitle");
});

test("Markdown renders inline bold, italic, and code", () => {
  const { container } = render(
    <Markdown source="this is **bold** and *italic* and `code` here." />
  );
  expect(container.querySelector("strong")?.textContent).toBe("bold");
  expect(container.querySelector("em")?.textContent).toBe("italic");
  expect(container.querySelector("code")?.textContent).toBe("code");
});

test("Markdown renders a fenced code block with the language data attribute", () => {
  const { container } = render(
    <Markdown source={"```ts\nconst x = 1;\n```"} />
  );
  const code = container.querySelector("pre code");
  expect(code).toBeDefined();
  expect(code?.textContent).toBe("const x = 1;");
  expect(code?.getAttribute("data-language")).toBe("ts");
});

test("Markdown renders a bullet list with three items", () => {
  const { container } = render(<Markdown source={"- one\n- two\n- three"} />);
  const items = container.querySelectorAll("li");
  expect(items.length).toBe(3);
  expect(items[0].textContent).toBe("one");
  expect(items[2].textContent).toBe("three");
});

test("Markdown renders ordered lists and block quotes", () => {
  const { container } = render(
    <Markdown source={"1. first\n2. second\n\n> quoted\n> source"} />
  );

  expect(container.querySelector("ol li")?.textContent).toBe("first");
  expect(container.querySelectorAll("ol li")[1]?.textContent).toBe("second");
  expect(container.querySelector("blockquote")?.textContent).toBe(
    "quotedsource"
  );
});

test("Markdown renders a link with href + text", () => {
  const { container } = render(
    <Markdown source="see [docs](https://example.com) for more" />
  );
  const link = container.querySelector("a");
  expect(link?.getAttribute("href")).toBe("https://example.com");
  expect(link?.textContent).toBe("docs");
});

test("Markdown does not render executable link hrefs", () => {
  const { container } = render(
    <Markdown source="bad [link](javascript:alert(1)) stays text" />
  );

  expect(container.querySelector("a")).toBeNull();
  expect(container.textContent).toContain("link");
  expect(container.innerHTML).not.toContain("javascript:");
});

test("Markdown component overrides replace the default anchor (MDX-style)", () => {
  const { container } = render(
    <Markdown
      source="visit [home](/home) please"
      components={{
        a: ({ href, children }) => (
          <span data-citation-href={href}>{children}</span>
        )
      }}
    />
  );
  // Default <a> should not render because the override took over.
  expect(container.querySelector("a")).toBeNull();
  const chip = container.querySelector("[data-citation-href]");
  expect(chip?.getAttribute("data-citation-href")).toBe("/home");
  expect(chip?.textContent).toBe("home");
});
