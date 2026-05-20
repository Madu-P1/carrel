import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  },
  test: {
    environment: "jsdom",
    // T12 flipped VITE_RETRIEVAL_USE_NODES default-on, so production
    // AskView (CARDS_MODE) renders the typed-node card list. The
    // AskView integration suites (ask-view.test.tsx, ask-view-empty-
    // state.test.tsx, the app-shell Ask-route cases) assert the legacy
    // synthesised-answer renderer, which is the VITE_RETRIEVAL_USE_NODES
    // = "false" build path. Pin the flag off for the test run so those
    // suites exercise the path they were written for; this matches the
    // pre-T12 default. The card UI is covered by tests/ask/ask-cards.test.tsx.
    env: {
      VITE_RETRIEVAL_USE_NODES: "false"
    },
    fileParallelism: false,
    globals: false,
    maxWorkers: 1,
    minWorkers: 1,
    poolOptions: {
      threads: {
        singleThread: true
      }
    },
    setupFiles: ["./tests/setup.ts"]
  }
});
