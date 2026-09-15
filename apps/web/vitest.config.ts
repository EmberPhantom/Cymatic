import { defineConfig } from "vitest/config"
import { fileURLToPath } from "node:url"

export default defineConfig({
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    pool: "forks",
    fileParallelism: false,
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "cobertura"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      thresholds: {
        // Baseline ratchet: codebase currently ~2% covered (3 test files).
        // Raise incrementally as hooks/lib/components gain tests; do not lower.
        lines: 1,
        functions: 1,
        branches: 1,
        statements: 1,
      },
    },
  },
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
})
