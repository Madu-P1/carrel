const ALLOWED_NOTE_TAGS = new Set([
  "BLOCKQUOTE",
  "BR",
  "CODE",
  "DIV",
  "EM",
  "H1",
  "H2",
  "H3",
  "LI",
  "OL",
  "P",
  "PRE",
  "S",
  "STRONG",
  "U",
  "UL"
]);

const DROP_NOTE_TAGS = new Set([
  "APPLET",
  "AUDIO",
  "CANVAS",
  "EMBED",
  "FORM",
  "IFRAME",
  "IMG",
  "INPUT",
  "LINK",
  "MATH",
  "META",
  "OBJECT",
  "SCRIPT",
  "SOURCE",
  "STYLE",
  "SVG",
  "TEMPLATE",
  "VIDEO"
]);

const RENAME_NOTE_TAGS = new Map([
  ["B", "STRONG"],
  ["I", "EM"],
  ["STRIKE", "S"]
]);

export function sanitizeNoteHtml(raw: string | null | undefined): string {
  if (raw == null || raw === "" || raw === "\n") return "\n";
  if (typeof document === "undefined") return escapeHtml(raw);

  const template = document.createElement("template");
  template.innerHTML = raw;
  sanitizeChildren(template.content);

  const html = template.innerHTML;
  return html.trim() === "" || html.trim() === "<br>" ? "\n" : html;
}

function sanitizeChildren(parent: ParentNode): void {
  for (const node of Array.from(parent.childNodes)) {
    if (node.nodeType === Node.COMMENT_NODE) {
      node.remove();
      continue;
    }
    if (node.nodeType !== Node.ELEMENT_NODE) continue;

    const element = node as HTMLElement;
    const replacementName = RENAME_NOTE_TAGS.get(element.tagName);
    const effectiveName = replacementName ?? element.tagName;

    if (DROP_NOTE_TAGS.has(element.tagName)) {
      element.remove();
      continue;
    }

    sanitizeChildren(element);

    if (!ALLOWED_NOTE_TAGS.has(effectiveName)) {
      element.replaceWith(...Array.from(element.childNodes));
      continue;
    }

    for (const attr of Array.from(element.attributes)) {
      element.removeAttribute(attr.name);
    }

    if (replacementName) {
      const replacement = document.createElement(replacementName.toLowerCase());
      replacement.append(...Array.from(element.childNodes));
      element.replaceWith(replacement);
    }
  }
}

function escapeHtml(raw: string): string {
  return raw
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
