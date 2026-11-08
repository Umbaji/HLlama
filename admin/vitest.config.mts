import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests of the back office: what the code sends to the API and what it
// accepts back. Coverage is measured over every source file, pages
// included, so the figure is the share of the whole back office.
export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  esbuild: { jsx: "automatic" },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test/setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/**/*.test.{ts,tsx}", "src/test/**"],
      reporter: ["text-summary", "text", "json-summary", "html"],
      thresholds: { statements: 15 },
    },
  },
});
