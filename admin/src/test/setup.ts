import { vi } from "vitest";

// next-intl/server refuses to run outside a Next.js server. Its
// getRequestConfig only hands the function back, so the tests call
// src/i18n/request.ts directly, the way Next would.
vi.mock("next-intl/server", () => ({
  getRequestConfig: <T>(load: T) => load,
}));
