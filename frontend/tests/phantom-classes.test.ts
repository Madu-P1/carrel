import { readdirSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

import { describe, expect, it } from "vitest";

/**
 * The phantom-class lock. CSS modules fail open: `styles.foo` for a class the
 * module never defines is `undefined`, the element silently renders
 * class="undefined", and every visual rule meant for it is absent — no type
 * error, no test failure, no console noise. This branch shipped exactly that
 * (a parallel-edit merge dropped a CSS slice while the TSX kept referencing
 * it, unstyling the settled verdict bar and the streaming skeletons), so the
 * invariant is now pinned: every `styles.<name>` reference in a component
 * must resolve to a class defined in the module it imports.
 */

const SRC = resolve(__dirname, "../src");

function walk(dir: string): string[] {
  const out: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "node_modules" || entry.name.startsWith(".")) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...walk(full));
    else if (/\.(tsx|ts)$/.test(entry.name) && !/\.test\.tsx?$/.test(entry.name)) out.push(full);
  }
  return out;
}

/** Class names defined in a CSS module: `.name` selectors plus composes. */
function definedClasses(cssText: string): Set<string> {
  const names = new Set<string>();
  for (const [, name] of cssText.matchAll(/\.([A-Za-z_][\w-]*)/g)) names.add(name);
  return names;
}

describe("every styles.<name> reference resolves to a defined CSS-module class", () => {
  const failures: string[] = [];

  for (const file of walk(SRC)) {
    const source = readFileSync(file, "utf8");
    // Match every `import <ident> from "<path>.module.css"` (styles, verifyStyles, …).
    for (const [, ident, spec] of source.matchAll(
      /import\s+(\w+)\s+from\s+"([^"]+\.module\.css)"/g
    )) {
      const cssPath = spec.startsWith("@/")
        ? join(SRC, spec.slice(2))
        : resolve(dirname(file), spec);
      let cssText: string;
      try {
        cssText = readFileSync(cssPath, "utf8");
      } catch {
        failures.push(`${file}: cannot read ${spec}`);
        continue;
      }
      const defined = definedClasses(cssText);
      for (const [, name] of source.matchAll(new RegExp(`\\b${ident}\\.([A-Za-z_][\\w]*)`, "g"))) {
        if (!defined.has(name)) {
          failures.push(`${file}: ${ident}.${name} has no .${name} in ${spec}`);
        }
      }
    }
  }

  it("finds no phantom class references", () => {
    expect(failures, failures.join("\n")).toEqual([]);
  });
});
