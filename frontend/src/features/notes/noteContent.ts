import { sanitizeNoteHtml } from "./sanitizeNoteHtml";

const HTML_TAG_RE = /<\/?[a-z][\s\S]*>/i;
const HTML_ENTITY_RE = /&(?:nbsp|amp|lt|gt|quot|apos|#\d+|#x[0-9a-f]+);/i;

export function noteContentToMarkdown(
  content: string | null | undefined
): string {
  if (content == null || content === "" || content === "\n") return "";
  if (!looksLikeHtml(content)) return normalizeMarkdown(content);
  if (typeof document === "undefined") {
    return normalizeMarkdown(content.replace(/<[^>]+>/g, " "));
  }

  const cleanHtml = sanitizeNoteHtml(content);
  if (cleanHtml === "\n") return "";

  const template = document.createElement("template");
  template.innerHTML = cleanHtml;
  return normalizeMarkdown(
    renderNodesAsMarkdown(Array.from(template.content.childNodes), false)
  );
}

export function serializeNoteMarkdown(draft: string): string {
  const normalized = normalizeMarkdown(draft);
  return normalized.trim() === "" ? "\n" : normalized;
}

export function notePreviewText(
  content: string | null | undefined,
  fallback = "Start writing..."
): string {
  const markdown = noteContentToMarkdown(content);
  const text = markdown
    .replace(/```[\s\S]*?```/g, (match) =>
      match.replace(/^```[^\n]*\n?/, "").replace(/\n?```$/, "")
    )
    .replace(/!\[([^\]]*)\]\([^)]+\)/g, "$1")
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    .replace(/^#{1,6}\s+/gm, "")
    .replace(/^\s*[-*]\s+/gm, "")
    .replace(/^\s*\d+\.\s+/gm, "")
    .replace(/^\s*>\s?/gm, "")
    .replace(/[*_~`]+/g, "")
    .replace(/\s+/g, " ")
    .trim();
  return text || fallback;
}

function looksLikeHtml(content: string): boolean {
  return HTML_TAG_RE.test(content) || HTML_ENTITY_RE.test(content);
}

function renderNodesAsMarkdown(
  nodes: ChildNode[],
  keepWhitespaceOnlyText: boolean
): string {
  return nodes
    .map((node) => renderNodeAsMarkdown(node, keepWhitespaceOnlyText))
    .join("");
}

function renderNodeAsMarkdown(
  node: ChildNode,
  keepWhitespaceOnlyText: boolean
): string {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent ?? "";
    return keepWhitespaceOnlyText || text.trim() !== "" ? text : "";
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return "";

  const element = node as HTMLElement;
  const inline = () =>
    renderNodesAsMarkdown(Array.from(element.childNodes), true);
  const block = (text: string) => `${text.trim()}\n\n`;

  switch (element.tagName) {
    case "BR":
      return "\n";
    case "P":
    case "DIV":
      return block(inline());
    case "H1":
      return block(`# ${inline()}`);
    case "H2":
      return block(`## ${inline()}`);
    case "H3":
      return block(`### ${inline()}`);
    case "STRONG":
      return `**${inline()}**`;
    case "EM":
      return `*${inline()}*`;
    case "S":
      return `~~${inline()}~~`;
    case "U":
      return inline();
    case "CODE":
      return element.parentElement?.tagName === "PRE"
        ? inline()
        : `\`${inline()}\``;
    case "PRE":
      return block(`\`\`\`\n${element.textContent ?? ""}\n\`\`\``);
    case "BLOCKQUOTE":
      return block(
        inline()
          .trim()
          .split("\n")
          .map((line) => `> ${line}`)
          .join("\n")
      );
    case "UL":
      return block(renderListItems(element, false));
    case "OL":
      return block(renderListItems(element, true));
    case "LI":
      return inline();
    default:
      return inline();
  }
}

function renderListItems(list: HTMLElement, ordered: boolean): string {
  return Array.from(list.children)
    .filter((child) => child.tagName === "LI")
    .map((child, index) => {
      const marker = ordered ? `${index + 1}.` : "-";
      const text = renderNodesAsMarkdown(
        Array.from(child.childNodes),
        true
      ).trim();
      return `${marker} ${text}`;
    })
    .join("\n");
}

function normalizeMarkdown(markdown: string): string {
  return decodeHtmlEntities(markdown)
    .replace(/\r\n/g, "\n")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

const NAMED_HTML_ENTITIES: Record<string, string> = {
  nbsp: " ",
  amp: "&",
  lt: "<",
  gt: ">",
  quot: '"',
  apos: "'",
};

// Decode the small set of named + numeric HTML entities that
// `HTML_ENTITY_RE` recognises. Done in pure JS rather than the common
// `textarea.innerHTML = value; return textarea.value` shortcut because
// that pattern routes user-controlled bytes through the HTML parser
// (CodeQL js/xss-through-dom). For sanitised note markdown this set
// of entities is enough; anything else either passes through verbatim
// or is stripped earlier by sanitizeNoteHtml.
function decodeHtmlEntities(value: string): string {
  if (!HTML_ENTITY_RE.test(value)) return value;
  return value.replace(
    /&(nbsp|amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);/gi,
    (match, entity: string) => {
      const named = NAMED_HTML_ENTITIES[entity.toLowerCase()];
      if (named !== undefined) return named;
      if (entity.startsWith("#x") || entity.startsWith("#X")) {
        const code = Number.parseInt(entity.slice(2), 16);
        return Number.isFinite(code) ? String.fromCodePoint(code) : match;
      }
      if (entity.startsWith("#")) {
        const code = Number.parseInt(entity.slice(1), 10);
        return Number.isFinite(code) ? String.fromCodePoint(code) : match;
      }
      return match;
    }
  );
}
