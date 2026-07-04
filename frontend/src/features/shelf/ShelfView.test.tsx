import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";

import { briefs as briefsApi, type BriefSummary } from "@/services/api/endpoints";
import { navigateTo } from "@/app/shell/useAppShell";

import { ShelfView } from "./ShelfView";

// The Shelf is a data-fetching view; mock the endpoints module so the test
// drives load/empty/list/delete deterministically. Design-system primitives
// render for real (jsdom), matching the house component-test convention.
vi.mock("@/services/api/endpoints", () => ({
  briefs: {
    list: vi.fn(),
    remove: vi.fn()
  }
}));

vi.mock("@/app/shell/useAppShell", () => ({ navigateTo: vi.fn() }));

const mockList = vi.mocked(briefsApi.list);
const mockRemove = vi.mocked(briefsApi.remove);
const mockNavigate = vi.mocked(navigateTo);

const FP = "abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789";

function summary(overrides: Partial<BriefSummary> = {}): BriefSummary {
  return {
    id: "b1",
    title: "Motion to Dismiss",
    fingerprint: FP,
    seal_state: "sealed",
    created_at: "2026-01-02T00:00:00+00:00",
    updated_at: "2026-01-02T00:00:00+00:00",
    ...overrides
  };
}

afterEach(() => {
  vi.clearAllMocks();
});

describe("ShelfView", () => {
  it("shows the empty state when no briefs are saved", async () => {
    mockList.mockResolvedValue({ briefs: [] });
    render(<ShelfView />);
    expect(await screen.findByText("Nothing on the shelf yet")).toBeTruthy();
    expect(
      screen.getByText("Verify a draft, then seal it to keep the checked record here.")
    ).toBeTruthy();
  });

  it("renders saved briefs with their seal labels and a short fingerprint", async () => {
    mockList.mockResolvedValue({
      briefs: [
        summary(),
        summary({
          id: "b2",
          title: "Reply Brief",
          seal_state: "unsealed",
          fingerprint: "1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef"
        })
      ]
    });
    render(<ShelfView />);

    expect(await screen.findByText("Motion to Dismiss")).toBeTruthy();
    expect(screen.getByText("Reply Brief")).toBeTruthy();
    // Handoff §8: per-row seal badges (SEAL INTACT / UNSEALED), one flat list.
    expect(screen.getByText("SEAL INTACT")).toBeTruthy();
    expect(screen.getByText("UNSEALED")).toBeTruthy();
    // The fingerprint renders shortened, never the full 64 hex chars.
    expect(screen.getByText("1234567890ab…")).toBeTruthy();
  });

  it("badges each brief by its own seal state (no silent mixing)", async () => {
    mockList.mockResolvedValue({
      briefs: [
        summary({ id: "b1", title: "Motion to Dismiss", seal_state: "sealed" }),
        summary({ id: "b2", title: "Reply Brief", seal_state: "unsealed" })
      ]
    });
    render(<ShelfView />);

    await screen.findByText("Motion to Dismiss");
    // One flat list; the badge on each row carries the seal state (a cracked
    // seal is derived on reopen, so the list never claims it).
    const rows = document.querySelectorAll("li");
    expect(rows.length).toBe(2);
    expect(screen.getByText("SEAL INTACT")).toBeTruthy();
    expect(screen.getByText("UNSEALED")).toBeTruthy();
  });

  it("marks each spine row with its seal state so the gutter ink and disc can key off it", async () => {
    mockList.mockResolvedValue({
      briefs: [
        summary({ id: "b1", title: "Motion to Dismiss", seal_state: "sealed" }),
        summary({ id: "b2", title: "Reply Brief", seal_state: "unsealed" })
      ]
    });
    render(<ShelfView />);

    await screen.findByText("Motion to Dismiss");
    const sealedRow = screen.getByText("Motion to Dismiss").closest("li");
    const unsealedRow = screen.getByText("Reply Brief").closest("li");
    expect(sealedRow?.getAttribute("data-sealed")).toBe("true");
    expect(unsealedRow?.getAttribute("data-sealed")).toBe("false");
  });

  it("falls back to 'Untitled brief' when a brief has no title", async () => {
    mockList.mockResolvedValue({ briefs: [summary({ title: null })] });
    render(<ShelfView />);
    expect(await screen.findByText("Untitled brief")).toBeTruthy();
  });

  it("requires a confirm step before deleting, then removes the row", async () => {
    mockList.mockResolvedValue({ briefs: [summary()] });
    mockRemove.mockResolvedValue({ deleted: true, brief_id: "b1" });
    render(<ShelfView />);

    await screen.findByText("Motion to Dismiss");
    // The resting delete trigger is the bin icon button, reached by aria-label.
    // First click only arms the confirm; nothing deleted yet.
    fireEvent.click(screen.getByRole("button", { name: "Delete Motion to Dismiss" }));
    expect(screen.getByText("Confirm")).toBeTruthy();
    expect(mockRemove).not.toHaveBeenCalled();

    fireEvent.click(screen.getByText("Confirm"));
    await waitFor(() => expect(mockRemove).toHaveBeenCalledWith("b1"));
    await waitFor(() => expect(screen.queryByText("Motion to Dismiss")).toBeNull());
  });

  it("can cancel an armed delete without removing anything", async () => {
    mockList.mockResolvedValue({ briefs: [summary()] });
    render(<ShelfView />);

    await screen.findByText("Motion to Dismiss");
    fireEvent.click(screen.getByRole("button", { name: "Delete Motion to Dismiss" }));
    fireEvent.click(screen.getByText("Cancel"));
    expect(mockRemove).not.toHaveBeenCalled();
    expect(screen.getByText("Motion to Dismiss")).toBeTruthy();
  });

  it("surfaces a load error with a retry affordance", async () => {
    mockList.mockRejectedValueOnce(new Error("network down"));
    render(<ShelfView />);
    expect(await screen.findByText("network down")).toBeTruthy();
    expect(screen.getByText("Reload the Shelf")).toBeTruthy();

    // Retry re-calls the endpoint and recovers.
    mockList.mockResolvedValue({ briefs: [summary()] });
    fireEvent.click(screen.getByText("Reload the Shelf"));
    expect(await screen.findByText("Motion to Dismiss")).toBeTruthy();
  });

  it("opens a brief by navigating to /verify?brief=<id> on the row's open target", async () => {
    mockList.mockResolvedValue({ briefs: [summary()] });
    render(<ShelfView />);
    await screen.findByText("Motion to Dismiss");

    fireEvent.click(screen.getByRole("button", { name: "Open Motion to Dismiss" }));
    expect(mockNavigate).toHaveBeenCalledWith("/verify?brief=b1");
  });

  it("does not navigate when the destructive Delete control is clicked", async () => {
    mockList.mockResolvedValue({ briefs: [summary()] });
    render(<ShelfView />);
    await screen.findByText("Motion to Dismiss");

    fireEvent.click(screen.getByRole("button", { name: "Delete Motion to Dismiss" }));
    // Delete arms the confirm; it must never double as navigation.
    expect(mockNavigate).not.toHaveBeenCalled();
    expect(screen.getByText("Confirm")).toBeTruthy();
  });
});
