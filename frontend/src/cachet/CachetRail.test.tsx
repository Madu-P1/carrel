import { render } from "@testing-library/preact";
import { describe, expect, it, vi } from "vitest";

import { CachetRail } from "./CachetRail";
import styles from "./cachet.module.css";

// navigateTo is only called on click; the rail's active-state logic is what we
// guard here, so a no-op mock keeps the import from reaching into the app shell.
vi.mock("@/app/shell/useAppShell", () => ({ navigateTo: vi.fn() }));

// Regression for the reported bug: isActive special-cased itemPath === "/verify",
// but no rail item uses that path (Verify's path is "/"). The dead branch let
// Verify fall through to startsWith("/"), which is true on EVERY route, so the
// Verify glyph lit up active alongside the real station on /shelf, /vault, and
// /settings -- two active glyphs and two aria-current="page" at once, which
// breaks single-active-station semantics for assistive tech. Exactly one glyph
// is active per route.

function activeGlyphs(container: Element): Element[] {
  return Array.from(
    container.querySelectorAll(`.${styles.glyphActive}`)
  );
}

function currentPageButtons(container: Element): Element[] {
  return Array.from(container.querySelectorAll('[aria-current="page"]'));
}

const ROUTES = ["/", "/shelf", "/vault", "/settings"];

describe("CachetRail active station", () => {
  for (const route of ROUTES) {
    it(`lights exactly one glyph on ${route}`, () => {
      const { container } = render(<CachetRail currentPath={route} />);
      expect(activeGlyphs(container)).toHaveLength(1);
    });

    it(`emits exactly one aria-current="page" on ${route}`, () => {
      const { container } = render(<CachetRail currentPath={route} />);
      expect(currentPageButtons(container)).toHaveLength(1);
    });
  }

  it("maps each route to its own station (mutually exclusive)", () => {
    const labelFor = (route: string): string => {
      const { container } = render(<CachetRail currentPath={route} />);
      const active = activeGlyphs(container);
      expect(active).toHaveLength(1);
      return active[0].getAttribute("aria-label") ?? "";
    };
    expect(labelFor("/")).toBe("Lectern");
    expect(labelFor("/shelf")).toBe("Shelf");
    expect(labelFor("/vault")).toBe("Vault");
    expect(labelFor("/settings")).toBe("Settings");
  });

  it("keeps Verify the active station on a /verify sub-route", () => {
    const { container } = render(<CachetRail currentPath="/verify" />);
    const active = activeGlyphs(container);
    expect(active).toHaveLength(1);
    expect(active[0].getAttribute("aria-label")).toBe("Lectern");
  });
});
