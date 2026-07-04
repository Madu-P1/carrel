import { fireEvent, render, screen, waitFor } from "@testing-library/preact";
import { describe, expect, it } from "vitest";

import specimenCert from "./__fixtures__/specimen-cert.json";
import { SealBenchView } from "./SealBenchView";

const GOOD = JSON.stringify(specimenCert);

function paste(value: string) {
  const area = screen.getByLabelText(/certificate to check/i);
  fireEvent.input(area, { target: { value } });
}

describe("SealBenchView (the connector: check any surface's record offline)", () => {
  it("verifies a kernel-issued seal and renders the exhibit", async () => {
    render(<SealBenchView />);
    paste(GOOD);
    await waitFor(() => expect(screen.getByText(/seal intact/i)).toBeTruthy());
    // The exhibit reads the record: ruling + tally + per-statement rulings.
    // "Altered from the record" appears twice on purpose (the overall ruling
    // and the one altered statement), so assert on the record + the tally.
    expect(screen.getByLabelText(/attestation record/i)).toBeTruthy();
    expect(screen.getAllByText(/altered from the record/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText(/verified against the record/i)).toBeTruthy();
  });

  it("refuses a tampered record loudly and withholds the exhibit", async () => {
    const forged = JSON.parse(GOOD);
    forged.claims[1].state = "verified"; // flip an altered verdict to a green
    render(<SealBenchView />);
    paste(JSON.stringify(forged));
    await waitFor(() => expect(screen.getByText(/seal broken/i)).toBeTruthy());
    // Nothing below a broken seal may be shown as an authoritative record.
    expect(screen.queryByLabelText(/attestation record/i)).toBeNull();
  });

  it("refuses non-certificate input with a plain reason", async () => {
    render(<SealBenchView />);
    paste('{"hello": "world"}');
    await waitFor(() =>
      expect(screen.getAllByText(/not a certificate/i).length).toBeGreaterThan(0)
    );
    expect(screen.queryByText(/seal intact/i)).toBeNull();
  });

  it("refuses text that is not JSON", async () => {
    render(<SealBenchView />);
    paste("this is not json at all");
    await waitFor(() => expect(screen.getByText(/not json/i)).toBeTruthy());
  });

  it("returns to the empty state when cleared", async () => {
    render(<SealBenchView />);
    paste(GOOD);
    await waitFor(() => expect(screen.getByText(/seal intact/i)).toBeTruthy());
    paste("");
    await waitFor(() => expect(screen.queryByText(/seal intact/i)).toBeNull());
  });
});
