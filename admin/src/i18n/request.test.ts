import { describe, expect, it } from "vitest";
import { messagesFor } from "@/test/intl";

function keys(value: unknown, prefix = ""): string[] {
  if (typeof value !== "object" || value === null) return [prefix];
  return Object.entries(value).flatMap(([k, v]) => keys(v, prefix ? `${prefix}.${k}` : k));
}

describe("the messages", () => {
  it("are served in the locale asked for", async () => {
    expect((await messagesFor("en")).locale).toBe("en");
  });

  it("fall back to French for a locale the back office does not have", async () => {
    expect((await messagesFor("ee")).locale).toBe("fr");
  });

  it("have the same keys in French and in English", async () => {
    const fr = keys((await messagesFor("fr")).messages).sort();
    const en = keys((await messagesFor("en")).messages).sort();
    expect(en).toEqual(fr);
  });
});
