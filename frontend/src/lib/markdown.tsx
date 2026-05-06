import type { VNode } from "preact";

/**
 * Minimal markdown renderer for tutor output.
 *
 * The Claude tutor emits plain-ish prose with occasional `**emphasis**`,
 * `*italic*`, inline `` `code` ``, paragraph breaks, and short bullet or
 * numbered lists. Rendering those as literal punctuation looks broken; pulling
 * in `marked` or `markdown-it` ships ~15-30 KB gz and a full HTML sanitizer
 * surface for nine characters worth of syntax.
 *
 * Scope (intentionally small):
 *   - paragraphs split on blank lines
 *   - `- ` / `* ` bullet lists, `N. ` ordered lists (contiguous runs)
 *   - inline `**bold**`, `*italic*`, and `` `code` ``
 *   - single newline inside a paragraph → `<br>`
 *
 * Out of scope: headings, block quotes, fenced code, tables, links, images,
 * raw HTML, auto-linking, KaTeX math, nested emphasis. Claude output rarely
 * needs these in the tutor path, and each is an XSS surface.
 *
 * Security model: the renderer returns JSX only. Every user-supplied string
 * enters the tree as a text-node child of a Preact element (never via
 * `dangerouslySetInnerHTML`), so Preact's built-in text escaping handles the
 * XSS surface for free. Adversarial input like `<script>` lands in a text
 * node; the DOM renders it as visible text, never as markup.
 */

// Inline parser. Matches **bold**, *italic*, and `code` in that order so that
// `**bold**` does not get parsed as two italics. Unbalanced delimiters render
// literally because the regex requires a matching closer with non-delimiter
// content in between.
const INLINE_PATTERN = /(\*\*([^*\n]+)\*\*|\*([^*\n]+)\*|`([^`\n]+)`)/g;

function parseInline(source: string, keyPrefix: string): (VNode | string)[] {
  const out: (VNode | string)[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let k = 0;
  INLINE_PATTERN.lastIndex = 0;
  while ((match = INLINE_PATTERN.exec(source)) !== null) {
    if (match.index > lastIndex) {
      out.push(source.slice(lastIndex, match.index));
    }
    const key = `${keyPrefix}-i-${k++}`;
    if (match[2] !== undefined) {
      out.push(<strong key={key}>{match[2]}</strong>);
    } else if (match[3] !== undefined) {
      out.push(<em key={key}>{match[3]}</em>);
    } else if (match[4] !== undefined) {
      out.push(<code key={key}>{match[4]}</code>);
    }
    lastIndex = INLINE_PATTERN.lastIndex;
  }
  if (lastIndex < source.length) {
    out.push(source.slice(lastIndex));
  }
  return out;
}

// Split a paragraph's text on single newlines and interleave <br>.
function renderParagraphContent(source: string, keyPrefix: string): (VNode | string)[] {
  const lines = source.split("\n");
  if (lines.length === 1) {
    // split() on a non-empty string always returns ≥1 element; gated on
    // length === 1 above, so [0] is defined.
    return parseInline(lines[0]!, keyPrefix);
  }
  const out: (VNode | string)[] = [];
  lines.forEach((line, i) => {
    if (i > 0) out.push(<br key={`${keyPrefix}-br-${i}`} />);
    out.push(...parseInline(line, `${keyPrefix}-ln-${i}`));
  });
  return out;
}

interface Block {
  kind: "paragraph" | "ul" | "ol";
  lines: string[];
}

// Group consecutive lines into blocks. Lists are runs of lines starting with
// `- ` / `* ` (ul) or `N. ` (ol). Blank lines reset to a new block.
function toBlocks(source: string): Block[] {
  const blocks: Block[] = [];
  let current: Block | null = null;
  const raw = source.replace(/\r\n/g, "\n").split("\n");

  const flush = () => {
    if (current && current.lines.length > 0) {
      blocks.push(current);
    }
    current = null;
  };

  for (const rawLine of raw) {
    const line = rawLine;
    if (line.trim() === "") {
      flush();
      continue;
    }
    const bulletMatch = /^\s*[-*]\s+(.*)$/.exec(line);
    const orderedMatch = /^\s*\d+\.\s+(.*)$/.exec(line);
    if (bulletMatch) {
      if (current?.kind !== "ul") {
        flush();
        current = { kind: "ul", lines: [] };
      }
      // Capture group 1 in the regex is non-optional, so when the
      // match succeeds the captured text is always defined.
      current.lines.push(bulletMatch[1]!);
    } else if (orderedMatch) {
      if (current?.kind !== "ol") {
        flush();
        current = { kind: "ol", lines: [] };
      }
      current.lines.push(orderedMatch[1]!);
    } else {
      if (current?.kind !== "paragraph") {
        flush();
        current = { kind: "paragraph", lines: [] };
      }
      current.lines.push(line);
    }
  }
  flush();
  return blocks;
}

export function renderMarkdown(source: string): VNode[] {
  if (!source) return [];
  const blocks = toBlocks(source);
  return blocks.map((block, i) => {
    const keyPrefix = `md-${i}`;
    if (block.kind === "paragraph") {
      return (
        <p key={keyPrefix}>
          {renderParagraphContent(block.lines.join("\n"), keyPrefix)}
        </p>
      );
    }
    if (block.kind === "ul") {
      return (
        <ul key={keyPrefix}>
          {block.lines.map((line, j) => (
            <li key={`${keyPrefix}-li-${j}`}>
              {parseInline(line, `${keyPrefix}-li-${j}`)}
            </li>
          ))}
        </ul>
      );
    }
    return (
      <ol key={keyPrefix}>
        {block.lines.map((line, j) => (
          <li key={`${keyPrefix}-li-${j}`}>
            {parseInline(line, `${keyPrefix}-li-${j}`)}
          </li>
        ))}
      </ol>
    );
  });
}

