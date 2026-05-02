import { fileURLToPath, URL } from "node:url";

import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

const isMacosBundleBuild = process.env.CARREL_MACOS_BUNDLE === "1";

export default defineConfig({
  base: "./",
  plugins: [preact()],
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: isMacosBundleBuild ? process.env.CARREL_DEBUG_SOURCEMAPS === "1" : true,
    target: "safari17",
    // The concepts graph and PDF reader intentionally live in lazy chunks.
    // three.js / 3d-force-graph are large even after splitting, but they are
    // not part of the initial app shell payload.
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name].js",
        chunkFileNames: "assets/[name].js",
        assetFileNames: "assets/[name].[ext]"
      }
    }
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url))
    }
  }
});
