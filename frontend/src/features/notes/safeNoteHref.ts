const BLOCKED_HREF_SCHEMES = ["javascript:", "data:", "vbscript:"];
const ALLOWED_HREF_PROTOCOLS = ["http:", "https:", "mailto:"];

export function safeNoteHref(href: string): string | null {
  const compact = href.replace(/\s+/g, "").toLowerCase();
  if (BLOCKED_HREF_SCHEMES.some((scheme) => compact.startsWith(scheme))) {
    return null;
  }

  try {
    const parsed = new URL(href, "https://carrel.local");
    if (ALLOWED_HREF_PROTOCOLS.includes(parsed.protocol)) return href;
  } catch {
    return null;
  }

  return href.startsWith("#") || href.startsWith("/") ? href : null;
}
