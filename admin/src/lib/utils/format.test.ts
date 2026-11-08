import { describe, expect, it } from "vitest";
import { cn } from "./cn";
import { formatAmount, formatDate, formatDateTime } from "./format";

describe("formatAmount", () => {
  it("writes francs CFA the way they are read in Togo", () => {
    expect(formatAmount(5000)).toMatch(/^5\s000 F CFA$/u);
  });

  it("keeps another currency's code", () => {
    expect(formatAmount(1500, "EUR", "en")).toBe("1,500 EUR");
  });
});

describe("formatDate", () => {
  it("in French by default", () => {
    expect(formatDate("2026-10-25")).toBe("25 oct. 2026");
  });

  it("in English", () => {
    expect(formatDate("2026-10-25", "en")).toBe("25 Oct 2026");
  });

  it("falls back to French for a locale it does not know", () => {
    expect(formatDate("2026-10-25", "ee")).toBe("25 oct. 2026");
  });

  it("with the time", () => {
    expect(formatDateTime("2026-10-25T09:05:00", "en")).toBe("25 Oct 2026 09:05");
  });
});

describe("cn", () => {
  it("keeps the last of two conflicting classes", () => {
    expect(cn("px-2", false && "hidden", "px-4")).toBe("px-4");
  });
});
