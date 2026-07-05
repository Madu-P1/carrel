import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import { SPECIMEN_DRAFT, SPECIMEN_RECORD } from "./LecternView";

/**
 * The one-click specimen demo's beats (the date drift, the capped-amount
 * drift, the exclusivity flip, the verified term, the verbatim jurisdiction
 * quote) are calibrated against the demo corpus that tests.test_demo_corpus
 * proves honest. The Lectern carries hand-copied excerpts; if the corpus is
 * re-vetted and the copies drift, the planted flags silently degrade into
 * refusals on the first-run demo. This lock ties the copies to the corpus.
 */

const DEMO = resolve(__dirname, "../../../demo");

function normalize(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

describe("the specimen stays in sync with the demo corpus", () => {
  it("every paragraph of the specimen record is verbatim in demo/contract-msa.md", () => {
    const corpus = normalize(readFileSync(resolve(DEMO, "contract-msa.md"), "utf8"));
    for (const paragraph of SPECIMEN_RECORD.split(/\n{2,}/)) {
      expect(corpus, `record paragraph drifted from the corpus:\n${paragraph}`).toContain(
        normalize(paragraph)
      );
    }
  });

  it("every contract line of the specimen draft is verbatim in demo/contract-ai-summary.md", () => {
    const summary = normalize(readFileSync(resolve(DEMO, "contract-ai-summary.md"), "utf8"));
    // The first two lines are the litigator beats (case-law store, not the
    // contract corpus); the rest are the pre-vetted AI-summary defect lines.
    const contractLines = SPECIMEN_DRAFT.split("\n").slice(2);
    expect(contractLines.length).toBeGreaterThan(0);
    for (const line of contractLines) {
      expect(summary, `draft line drifted from the vetted summary:\n${line}`).toContain(
        normalize(line)
      );
    }
  });
});
