import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { expect, test } from "vitest";

import { ToastHost } from "../../src/design-system";
import { CheckInWidget } from "../../src/features/plan/components/CheckInWidget";
import { jsonResponse, registerFetchHandler } from "../support/mockFetch";

/**
 * Pin the CheckInWidget UX contract:
 *   1. Submit disabled until both scales picked
 *   2. POST fires with the picked stress + energy
 *   3. Toast acknowledges success and form resets
 */

test("submit is disabled until both stress and energy are picked", () => {
  registerFetchHandler(() => undefined);

  render(<CheckInWidget />);

  const submit = screen.getByRole("button", { name: /^Log it$/i }) as HTMLButtonElement;
  expect(submit.disabled).toBe(true);

  // Pick stress only. Submit must still be disabled because energy is
  // unset. Scope the radio query to the Stress group to disambiguate
  // from the matching value in the Energy group.
  const stressGroup = screen.getByRole("radiogroup", { name: /Stress/i });
  fireEvent.click(stressGroup.querySelector('input[value="3"]')!);
  expect(submit.disabled).toBe(true);
});

test("submitting posts the selected values and resets the form", async () => {
  let captured: Record<string, unknown> | undefined;
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan/check-in" && init.method === "POST") {
      captured = JSON.parse(init.body as string);
      return jsonResponse({ id: "check-in-1", status: "recorded" });
    }
    return undefined;
  });

  render(
    <>
      <CheckInWidget />
      <ToastHost />
    </>
  );

  // Pick stress=4 in the Stress group, energy=2 in the Energy group.
  // Both radio rows render values 1..5, so disambiguate via the group.
  const stressGroup = screen.getByRole("radiogroup", { name: /Stress/i });
  const energyGroup = screen.getByRole("radiogroup", { name: /Energy/i });
  fireEvent.click(stressGroup.querySelector('input[value="4"]')!);
  fireEvent.click(energyGroup.querySelector('input[value="2"]')!);

  const submit = screen.getByRole("button", { name: /^Log it$/i }) as HTMLButtonElement;
  expect(submit.disabled).toBe(false);

  fireEvent.click(submit);

  // Toast appears, payload was sent.
  expect(await screen.findByText(/Coach is listening/i)).toBeDefined();
  await waitFor(() => {
    expect(captured).toEqual({ stress_level: 4, energy_level: 2 });
  });

  // Form resets: submit disabled again.
  await waitFor(() => {
    expect(submit.disabled).toBe(true);
  });
});

test("failed submission surfaces an error toast and leaves the form populated", async () => {
  registerFetchHandler((url, init) => {
    if (url.pathname === "/api/plan/check-in" && init.method === "POST") {
      return new Response("server explosion", { status: 500 });
    }
    return undefined;
  });

  render(
    <>
      <CheckInWidget />
      <ToastHost />
    </>
  );

  const stressGroup = screen.getByRole("radiogroup", { name: /Stress/i });
  const energyGroup = screen.getByRole("radiogroup", { name: /Energy/i });
  fireEvent.click(stressGroup.querySelector('input[value="3"]')!);
  fireEvent.click(energyGroup.querySelector('input[value="3"]')!);

  fireEvent.click(screen.getByRole("button", { name: /^Log it$/i }));

  expect(await screen.findByText(/Could not log check-in/i)).toBeDefined();

  // Form still has selections so the user can retry.
  const submit = screen.getByRole("button", { name: /^Log it$/i }) as HTMLButtonElement;
  await waitFor(() => expect(submit.disabled).toBe(false));
});
