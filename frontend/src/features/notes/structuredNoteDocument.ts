import { safeNoteHref } from "./safeNoteHref";

export interface StructuredMark {
  type: string;
  attrs?: Record<string, unknown>;
}

export interface StructuredNode {
  type: string;
  attrs?: Record<string, unknown>;
  text?: string;
  marks?: StructuredMark[];
  content?: StructuredNode[];
}

export function markdownToStructuredDoc(markdown: string): StructuredNode {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const content: StructuredNode[] = [];
  let index = 0;

  while (index < lines.length) {
    const line = lines[index] ?? "";
    if (line.trim() === "") {
      index += 1;
      continue;
    }

    if (line.startsWith("```")) {
      const code: string[] = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        code.push(lines[index]);
        index += 1;
      }
      if (index < lines.length) index += 1;
      content.push({
        type: "codeBlock",
        content: code.join("\n") ? [{ type: "text", text: code.join("\n") }] : []
      });
      continue;
    }

    const heading = /^(#{1,3})\s+(.+)$/.exec(line);
    if (heading) {
      content.push({
        type: "heading",
        attrs: { level: heading[1].length },
        content: parseInlineMarkdown(heading[2])
      });
      index += 1;
      continue;
    }

    if (/^\s*>\s?/.test(line)) {
      const quote: string[] = [];
      while (index < lines.length && /^\s*>\s?/.test(lines[index])) {
        quote.push(lines[index].replace(/^\s*>\s?/, ""));
        index += 1;
      }
      content.push({
        type: "blockquote",
        content: paragraphNodes(quote.join("\n"))
      });
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: StructuredNode[] = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) {
        items.push(listItem(lines[index].replace(/^\s*[-*]\s+/, "")));
        index += 1;
      }
      content.push({ type: "bulletList", content: items });
      continue;
    }

    if (/^\s*\d+\.\s+/.test(line)) {
      const items: StructuredNode[] = [];
      let start = 1;
      while (index < lines.length) {
        const match = /^\s*(\d+)\.\s+(.+)$/.exec(lines[index]);
        if (!match) break;
        if (items.length === 0) start = Number.parseInt(match[1], 10) || 1;
        items.push(listItem(match[2]));
        index += 1;
      }
      content.push({ type: "orderedList", attrs: { start }, content: items });
      continue;
    }

    const paragraph: string[] = [];
    while (index < lines.length && lines[index].trim() !== "") {
      if (isBlockStart(lines[index]) && paragraph.length > 0) break;
      paragraph.push(lines[index]);
      index += 1;
    }
    content.push({
      type: "paragraph",
      content: parseInlineMarkdown(paragraph.join(" "))
    });
  }

  return {
    type: "doc",
    content: content.length > 0 ? content : [{ type: "paragraph" }]
  };
}

export function structuredDocToMarkdown(doc: StructuredNode): string {
  return normalizeMarkdown(
    (doc.content ?? [])
      .map((node) => serializeNode(node))
      .filter((part) => part.trim() !== "")
      .join("\n\n")
  );
}

function paragraphNodes(text: string): StructuredNode[] {
  return [{ type: "paragraph", content: parseInlineMarkdown(text) }];
}

function listItem(text: string): StructuredNode {
  return { type: "listItem", content: paragraphNodes(text) };
}

function isBlockStart(line: string): boolean {
  return (
    line.startsWith("```") ||
    /^(#{1,3})\s+/.test(line) ||
    /^\s*>\s?/.test(line) ||
    /^\s*[-*]\s+/.test(line) ||
    /^\s*\d+\.\s+/.test(line)
  );
}

function parseInlineMarkdown(
  text: string,
  inheritedMarks: StructuredMark[] = []
): StructuredNode[] {
  const nodes: StructuredNode[] = [];
  let index = 0;

  const pushText = (value: string, marks = inheritedMarks) => {
    if (value === "") return;
    nodes.push({
      type: "text",
      text: value,
      marks: marks.length > 0 ? marks : undefined
    });
  };

  while (index < text.length) {
    if (text.startsWith("`", index)) {
      const end = text.indexOf("`", index + 1);
      if (end > index + 1) {
        pushText(text.slice(index + 1, end), [
          ...inheritedMarks,
          { type: "code" }
        ]);
        index = end + 1;
        continue;
      }
    }

    if (text.startsWith("**", index)) {
      const end = text.indexOf("**", index + 2);
      if (end > index + 2) {
        nodes.push(
          ...parseInlineMarkdown(text.slice(index + 2, end), [
            ...inheritedMarks,
            { type: "bold" }
          ])
        );
        index = end + 2;
        continue;
      }
    }

    if (text.startsWith("~~", index)) {
      const end = text.indexOf("~~", index + 2);
      if (end > index + 2) {
        nodes.push(
          ...parseInlineMarkdown(text.slice(index + 2, end), [
            ...inheritedMarks,
            { type: "strike" }
          ])
        );
        index = end + 2;
        continue;
      }
    }

    if (text.startsWith("*", index)) {
      const end = text.indexOf("*", index + 1);
      if (end > index + 1) {
        nodes.push(
          ...parseInlineMarkdown(text.slice(index + 1, end), [
            ...inheritedMarks,
            { type: "italic" }
          ])
        );
        index = end + 1;
        continue;
      }
    }

    if (text.startsWith("[", index)) {
      const labelEnd = text.indexOf("]", index + 1);
      const hrefStart = labelEnd >= 0 ? labelEnd + 1 : -1;
      if (hrefStart >= 0 && text[hrefStart] === "(") {
        const hrefEnd = findHrefEnd(text, hrefStart + 1);
        if (hrefEnd > hrefStart + 1) {
          const href = text.slice(hrefStart + 1, hrefEnd);
          const label = text.slice(index + 1, labelEnd);
          const linkMark = safeNoteHref(href);
          nodes.push(
            ...parseInlineMarkdown(
              label,
              linkMark
                ? [...inheritedMarks, { type: "link", attrs: { href: linkMark } }]
                : inheritedMarks
            )
          );
          index = hrefEnd + 1;
          continue;
        }
      }
    }

    const next = nextSpecialIndex(text, index + 1);
    pushText(text.slice(index, next));
    index = next;
  }

  return nodes;
}

function findHrefEnd(text: string, from: number): number {
  let depth = 0;
  for (let index = from; index < text.length; index += 1) {
    const char = text[index];
    if (char === "(") {
      depth += 1;
      continue;
    }
    if (char === ")") {
      if (depth === 0) return index;
      depth -= 1;
    }
  }
  return -1;
}

function nextSpecialIndex(text: string, from: number): number {
  const candidates = ["`", "*", "~", "["]
    .map((needle) => text.indexOf(needle, from))
    .filter((candidate) => candidate >= 0);
  return candidates.length > 0 ? Math.min(...candidates) : text.length;
}

function serializeNode(node: StructuredNode): string {
  switch (node.type) {
    case "heading": {
      const level = Number(node.attrs?.level) || 1;
      return `${"#".repeat(Math.min(Math.max(level, 1), 3))} ${serializeInline(node)}`;
    }
    case "paragraph":
      return serializeInline(node);
    case "bulletList":
      return serializeList(node, false);
    case "orderedList":
      return serializeList(node, true);
    case "listItem":
      return (node.content ?? []).map((child) => serializeNode(child)).join("\n");
    case "blockquote":
      return (node.content ?? [])
        .map((child) => serializeNode(child))
        .join("\n")
        .split("\n")
        .map((line) => `> ${line}`)
        .join("\n");
    case "codeBlock":
      return `\`\`\`\n${serializePlainText(node)}\n\`\`\``;
    case "hardBreak":
      return "\n";
    case "text":
      return serializeTextNode(node);
    default:
      return serializeInline(node);
  }
}

function serializeInline(node: StructuredNode): string {
  return (node.content ?? []).map((child) => serializeNode(child)).join("");
}

function serializeList(node: StructuredNode, ordered: boolean): string {
  const start = Number(node.attrs?.start) || 1;
  return (node.content ?? [])
    .map((child, index) => {
      const body = serializeNode(child).replace(/\n/g, "\n  ");
      return `${ordered ? `${start + index}.` : "-"} ${body}`;
    })
    .join("\n");
}

function serializePlainText(node: StructuredNode): string {
  if (node.text) return node.text;
  return (node.content ?? []).map((child) => serializePlainText(child)).join("");
}

function serializeTextNode(node: StructuredNode): string {
  let text = node.text ?? "";
  for (const mark of node.marks ?? []) {
    switch (mark.type) {
      case "bold":
        text = `**${text}**`;
        break;
      case "italic":
        text = `*${text}*`;
        break;
      case "strike":
        text = `~~${text}~~`;
        break;
      case "code":
        text = `\`${text}\``;
        break;
      case "link": {
        const href =
          typeof mark.attrs?.href === "string"
            ? safeNoteHref(mark.attrs.href)
            : null;
        if (href) text = `[${text}](${href})`;
        break;
      }
    }
  }
  return text;
}

function normalizeMarkdown(markdown: string): string {
  return markdown
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}
