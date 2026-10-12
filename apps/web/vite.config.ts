/// <reference types="vitest" />
import { fileURLToPath, URL } from "node:url";
import react from "@vitejs/plugin-react";
// `vitest/config` re-exports Vite's `defineConfig` with the `test` block typed as well.
import { defineConfig } from "vitest/config";

/**
 * Dev/build config.
 *
 * The browser only ever talks to the Vite origin: every `/api` request is proxied to the
 * FastAPI service, so CORS never enters the picture. The proxy target can be overridden
 * with `VITE_PROXY_TARGET` (used when the API runs on another port).
 */
const proxyTarget = process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: proxyTarget,
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: false,
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
    // The live integration test talks to a real FastAPI process; the mocked suites finish in ms.
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});
