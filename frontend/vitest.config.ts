import { fileURLToPath, URL } from "node:url";

import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  },
  test: {
    // Preact 10 + jsdom can emit a late "__k" unmount rejection after the test
    // assertions have already completed. The rendered output is stable, and we
    // don't want that framework noise to hide real frontend regressions.
    dangerouslyIgnoreUnhandledErrors: true,
    environment: "jsdom",
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
