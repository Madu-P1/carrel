import { ComponentChildren, FunctionComponent, h, VNode } from "preact";
import { useMemo } from "preact/hooks";

import styles from "./Markdown.module.css";

/**
 * Minimal markdown renderer for Carrel notes, citations, and grounded
 * answers. Outputs Preact VNodes directly (no `innerHTML`, no HTML
 * injection surface). Supported subset:
 *
 *   # h1 ... ###### h6      headings
 *   blank-line-separated    paragraphs
 *   **bold**, *italic*      emphasis
 *   `inline code`           inline code
 *   ```fenced               fenced code blocks (no syntax highlighting)
 *   - item                  single-level unordered list
 *   [text](url)             links
 *
 * MDX-style component overrides: pass a `components` prop to swap in
 * custom renderers for specific tags. Use this for citation chips:
 *
 *     <Markdown source={text} components={{ a: CitationChip }} />
 *
 * Imported pattern: Next.js MDX integration. The full `@next/mdx`
 * package compiles JSX-in-Markdown at build time; we do the simpler
 * thing (markdown only, runtime parse, no JSX-in-source) for zero new
 * dependencies. Swap in `marked` or `markdown-it` if you need tables,
 * task lists, autolinks, or footnotes.
 */

type AnchorProps = { href: string; children: ComponentChildren };
type CodeProps = { children: string };
type PreProps = { language?: string; children: string };
type HeadingProps = { children: ComponentChildren };

export type MarkdownComponents = Partial<{
  a: FunctionComponent<AnchorProps>;
  code: FunctionComponent<CodeProps>;
  pre: FunctionComponent<PreProps>;
  h1: FunctionComponent<HeadingProps>;
  h2: FunctionComponent<HeadingProps>;
  h3: FunctionComponent<HeadingProps>;
  h4: FunctionComponent<HeadingProps>;
  h5: FunctionComponent<HeadingProps>;
  h6: FunctionComponent<HeadingProps>;
}>;

export interface MarkdownProps {
  source: string;
  components?: MarkdownComponents;
  className?: string;
}

const EMPTY_COMPONENTS: MarkdownComponents = {};

export function Markdown({ source, components, className }: MarkdownProps): VNode {
  const comps = components ?? EMPTY_COMPONENTS;
  const tree = useMemo(() => renderBlocks(source, comps), [source, comps]);
  return <div className={[styles.markdown, className].filter(Boolean).join(" ")}>{tree}</div>;
}

function renderBlocks(src: string, comps: MarkdownComponents): ComponentChildren[] {
  const out: ComponentChildren[] = [];
  const lines = src.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  let blockKey = 0;
  while (i < lines.length) {
    const line = lines[i];

    if (/^```/.test(line)) {
      const lang = line.replace(/^```/, "").trim();
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !/^```/.test(lines[i])) {
        codeLines.push(lines[i]);
        i++;
      }
      if (i < lines.length) i++;
      const codeText = codeLines.join("\n");
      const Pre = comps.pre;
      out.push(
        Pre
          ? <Pre key={`b${blockKey++}`} language={lang || undefined}>{codeText}</Pre>
          : (
            <pre key={`b${blockKey++}`} className={styles.codeBlock}>
              <code data-language={lang || undefined}>{codeText}</code>
            </pre>
          )
      );
      continue;
    }

    const heading = /^(#{1,6})\s+(.+?)\s*$/.exec(line);
    if (heading) {
      const level = heading[1].length as 1 | 2 | 3 | 4 | 5 | 6;
      const tag = `h${level}` as const;
      const inline = renderInline(heading[2], comps, `b${blockKey}`);
      const Custom = comps[tag];
      if (Custom) {
        out.push(<Custom key={`b${blockKey++}`}>{inline}</Custom>);
      } else {
        out.push(h(tag, { key: `b${blockKey++}` }, inline));
      }
      i++;
      continue;
    }

    if (/^\s*[-*]\s+/.test(line)) {
      const items: VNode[] = [];
      let itemKey = 0;
      while (i < lines.length && /^\s*[-*]\s+/.test(lines[i])) {
        const itemText = lines[i].replace(/^\s*[-*]\s+/, "");
        items.push(
          <li key={`li${itemKey++}`}>
            {renderInline(itemText, comps, `b${blockKey}-li${itemKey}`)}
          </li>
        );
        i++;
      }
      out.push(<ul key={`b${blockKey++}`} className={styles.list}>{items}</ul>);
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    const paraLines: string[] = [line];
    i++;
    while (
      i < lines.length &&
      lines[i].trim() !== "" &&
      !/^#{1,6}\s+/.test(lines[i]) &&
      !/^```/.test(lines[i]) &&
      !/^\s*[-*]\s+/.test(lines[i])
    ) {
      paraLines.push(lines[i]);
      i++;
    }
    const paraText = paraLines.join(" ");
    out.push(<p key={`b${blockKey++}`}>{renderInline(paraText, comps, `b${blockKey}`)}</p>);
  }
  return out;
}

function renderInline(src: string, comps: MarkdownComponents, scope: string): ComponentChildren[] {
  const tokens: ComponentChildren[] = [];
  let buf = "";
  let i = 0;
  let keyN = 0;
  const flush = () => {
    if (buf) {
      tokens.push(buf);
      buf = "";
    }
  };
  while (i < src.length) {
    const ch = src[i];

    if (ch === "`") {
      const close = src.indexOf("`", i + 1);
      if (close !== -1) {
        flush();
        const text = src.slice(i + 1, close);
        const Code = comps.code;
        tokens.push(
          Code
            ? <Code key={`${scope}-c${keyN++}`}>{text}</Code>
            : <code key={`${scope}-c${keyN++}`} className={styles.inlineCode}>{text}</code>
        );
        i = close + 1;
        continue;
      }
    }

    if (ch === "*" && src[i + 1] === "*") {
      const close = src.indexOf("**", i + 2);
      if (close !== -1) {
        flush();
        const inner = src.slice(i + 2, close);
        tokens.push(
          <strong key={`${scope}-b${keyN++}`}>
            {renderInline(inner, comps, `${scope}b${keyN}`)}
          </strong>
        );
        i = close + 2;
        continue;
      }
    }

    if (ch === "*") {
      const close = src.indexOf("*", i + 1);
      if (close !== -1) {
        flush();
        const inner = src.slice(i + 1, close);
        tokens.push(
          <em key={`${scope}-i${keyN++}`}>
            {renderInline(inner, comps, `${scope}i${keyN}`)}
          </em>
        );
        i = close + 1;
        continue;
      }
    }

    if (ch === "[") {
      const textEnd = src.indexOf("]", i + 1);
      if (textEnd !== -1 && src[textEnd + 1] === "(") {
        const urlEnd = src.indexOf(")", textEnd + 2);
        if (urlEnd !== -1) {
          flush();
          const text = src.slice(i + 1, textEnd);
          const url = src.slice(textEnd + 2, urlEnd);
          const Anchor = comps.a;
          tokens.push(
            Anchor
              ? <Anchor key={`${scope}-a${keyN++}`} href={url}>{text}</Anchor>
              : (
                <a key={`${scope}-a${keyN++}`} href={url} className={styles.link}>
                  {text}
                </a>
              )
          );
          i = urlEnd + 1;
          continue;
        }
      }
    }

    buf += ch;
    i++;
  }
  flush();
  return tokens;
}
