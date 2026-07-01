import { fileURLToPath, URL } from "node:url";

import preact from "@preact/preset-vite";
import { defineConfig } from "vite";

const debugSourcemaps = process.env.CARREL_DEBUG_SOURCEMAPS === "1";

export default defineConfig({
  base: "./",
  plugins: [preact()],
  build: {
    outDir: "dist",
    assetsDir: "assets",
    sourcemap: debugSourcemaps ? "hidden" : false,
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
  },
  optimizeDeps: {
    // The security pin to esbuild 0.28 (package.json pnpm.overrides) breaks
    // Vite 6's default dev-prebundle target list ("chrome87..." + supported
    // overrides): 0.28 refuses to lower destructuring for it and the dev
    // server 500s on every dep. Dev-only knob; the shipped build keeps the
    // stricter build.target above.
    esbuildOptions: { target: "esnext" }
  }
});
