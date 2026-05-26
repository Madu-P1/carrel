import type { GroundedAnswerEnvelope } from "../types";

export const DEMO_ANSWER: GroundedAnswerEnvelope = {
  actions: [],
  answer:
    "Mitosis produces two genetically identical daughter cells used for growth and tissue maintenance.",
  cache_hit: true,
  citation_attempt_count: 2,
  citation_drop_count: 0,
  citation_repair_count: 0,
  citations: [
    {
      node_type: "body",
      node_id: "demo-1",
      content:
        "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.",
      document_id: "demo-doc-biology",
      document_name: "cell-division.md",
      label: "cell-division.md · Cell division basics",
      page_num: 1,
      score: 1,
      section: "Cell division basics",
      snippet:
        "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance."
    },
    {
      node_type: "body",
      node_id: "demo-2",
      content:
        "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete.",
      document_id: "demo-doc-biology",
      document_name: "cell-division.md",
      label: "cell-division.md · Cell-cycle regulation",
      page_num: 1,
      score: 1,
      section: "Cell-cycle regulation",
      snippet:
        "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete."
    }
  ],
  claims: [
    {
      text: "Mitosis creates two genetically identical daughter cells.",
      citations: [
        {
          node_type: "body",
      node_id: "demo-1",
          content:
            "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.",
          document_id: "demo-doc-biology",
          document_name: "cell-division.md",
          label: "cell-division.md · Cell division basics",
          page_num: 1,
          score: 1,
          section: "Cell division basics",
          snippet:
            "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance."
        }
      ]
    },
    {
      text: "Checkpoints pause progression if DNA is damaged.",
      citations: [
        {
          node_type: "body",
      node_id: "demo-2",
          content:
            "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete.",
          document_id: "demo-doc-biology",
          document_name: "cell-division.md",
          label: "cell-division.md · Cell-cycle regulation",
          page_num: 1,
          score: 1,
          section: "Cell-cycle regulation",
          snippet:
            "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete."
        }
      ]
    }
  ],
  error: null,
  grounded: true,
  input_tokens: 320,
  latency_ms: 4280,
  misconceptions: [],
  model: "claude-sonnet-4-6",
  momentum: {},
  output_tokens: 162,
  scaffold_steps: ["Contrast the checkpoint goals in G1, G2, and M phase."],
  scaffolds: ["Contrast the checkpoint goals in G1, G2, and M phase."],
  selected_concept: "Mitosis",
  source_cards: [],
  unsupported_spans: ["What role do growth factors play in initiating mitosis?"]
};

export const DEMO_FALLBACK: GroundedAnswerEnvelope = {
  actions: [],
  answer: "",
  cache_hit: false,
  citation_attempt_count: 2,
  citation_drop_count: 0,
  citation_repair_count: 0,
  citations: [],
  error: "claude_call_failed",
  claims: [
    {
      text:
        "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.",
      citations: [
        {
          node_type: "body",
      node_id: "demo-fallback-1",
          content:
            "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance.",
          document_id: "demo-doc-biology",
          document_name: "cell-division.md",
          label: "cell-division.md · Cell division basics",
          page_num: 1,
          score: 1,
          section: "Cell division basics",
          snippet:
            "Mitosis creates two genetically identical daughter cells and is used for growth and maintenance."
        }
      ]
    },
    {
      text:
        "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete.",
      citations: [
        {
          node_type: "body",
      node_id: "demo-fallback-2",
          content:
            "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete.",
          document_id: "demo-doc-biology",
          document_name: "cell-division.md",
          label: "cell-division.md · Cell-cycle regulation",
          page_num: 1,
          score: 1,
          section: "Cell-cycle regulation",
          snippet:
            "Cell-cycle checkpoints pause progression if DNA is damaged or if spindle attachment is incomplete."
        }
      ]
    }
  ],
  grounded: false,
  input_tokens: null,
  latency_ms: 0,
  misconceptions: [],
  model: "",
  momentum: {},
  output_tokens: null,
  scaffold_steps: [],
  scaffolds: [],
  selected_concept: null,
  source_cards: [],
  unsupported_spans: []
};
