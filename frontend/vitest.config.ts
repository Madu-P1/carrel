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
    fileParallelism: false,
    globals: false,
    // vitest 4 removed test.poolOptions and changed the default pool to "forks".
    // Pin "threads" + a single worker to preserve the pre-4.x singleThread behavior
    // (deterministic, low-memory runs for the three.js / pdfjs suites).
    pool: "threads",
    maxWorkers: 1,
    minWorkers: 1,
    setupFiles: ["./tests/setup.ts"]
  }
});
