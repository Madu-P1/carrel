import { fireEvent, render, screen, waitFor, within } from "@testing-library/preact";
import { expect, test, vi } from "vitest";

import { AddFeedDialog } from "../../src/features/plan/components/AddFeedDialog";

test("AddFeedDialog displays only masked calendar URL after submit", async () => {
  const rawUrl = "https://calendar.example.com/private/basic.ics?token=secret";
  const onSubmit = vi.fn(async () => ({
    feed: {
      id: "feed-1",
      label: "Private",
      url: "https://calendar.example.com/***",
      color: null,
      is_enabled: true,
      last_synced_at: null,
      last_successful_sync_at: null,
      consecutive_failures: 0,
      last_error: null
    },
    raw_url_echo: "https://calendar.example.com/***"
  }));

  render(<AddFeedDialog open onClose={() => {}} onSubmit={onSubmit} />);

  const dialog = screen.getByRole("dialog");
  fireEvent.input(within(dialog).getByLabelText(/^Name$/i), {
    target: { value: "Private" }
  });
  fireEvent.input(within(dialog).getByLabelText(/iCal URL/i), {
    target: { value: rawUrl }
  });
  fireEvent.click(within(dialog).getByRole("button", { name: /Add feed/i }));

  await waitFor(() => expect(onSubmit).toHaveBeenCalledWith({
    label: "Private",
    url: rawUrl,
    color: expect.any(String)
  }));

  expect(await within(dialog).findByText(/Stored as: https:\/\/calendar\.example\.com\/\*\*\*/i)).toBeDefined();
  expect(dialog.textContent).not.toContain(rawUrl);
});
