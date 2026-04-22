import { fireEvent, render, screen } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { Button } from "./Button";

test("Button renders children", () => {
  render(<Button>Launch</Button>);

  expect(screen.getByRole("button", { name: "Launch" })).toBeDefined();
});

test("Button fires click handlers", () => {
  const onClick = vi.fn();
  render(<Button onClick={onClick}>Click</Button>);

  fireEvent.click(screen.getByRole("button", { name: "Click" }));
  expect(onClick).toHaveBeenCalledTimes(1);
});

test("Button blocks clicks when disabled", () => {
  const onClick = vi.fn();
  render(
    <Button disabled onClick={onClick}>
      Disabled
    </Button>
  );

  (screen.getByRole("button", { name: "Disabled" }) as HTMLButtonElement).click();
  expect(onClick).not.toHaveBeenCalled();
});

test("Button marks loading state with aria-busy", () => {
  render(<Button isLoading>Saving</Button>);

  expect(screen.getByRole("button").getAttribute("aria-busy")).toBe("true");
});
