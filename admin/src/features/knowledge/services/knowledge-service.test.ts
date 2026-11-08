import { describe, expect, it } from "vitest";
import { applyCorpusDocument, fetchCorpus, fetchCorpusDocument, scanCorpus } from "./knowledge-service";
import { fakeApi, ok } from "@/test/fake-api";

const DOCUMENT = {
  slug: "dmpa-sc", title: "DMPA-SC", source: "OMS", source_url: "https://www.who.int/", published: "2024",
  language: "fr", characters: 1200, passages: 4,
};

describe("the documentary base", () => {
  it("lists the documents", async () => {
    const sent = fakeApi(() => ok([DOCUMENT]));
    await expect(fetchCorpus()).resolves.toEqual([DOCUMENT]);
    expect(sent[0]?.url).toBe("/api/knowledge/corpus");
  });

  it("reads one document with its content", async () => {
    fakeApi(() => ok({ ...DOCUMENT, content: "texte" }));
    await expect(fetchCorpusDocument("dmpa-sc")).resolves.toMatchObject({ content: "texte" });
  });

  it("a document without its source is refused", async () => {
    const withoutSource: Partial<typeof DOCUMENT> = { ...DOCUMENT };
    delete withoutSource.source;
    fakeApi(() => ok([withoutSource]));
    await expect(fetchCorpus()).rejects.toThrow();
  });

  it("a scan reports each document's status", async () => {
    const sent = fakeApi(() => ok([{ ...DOCUMENT, status: "changed", diff: "-a\n+b" }]));
    await expect(scanCorpus()).resolves.toMatchObject([{ status: "changed" }]);
    expect(sent[0]).toMatchObject({ method: "POST", url: "/api/knowledge/corpus/scan" });
  });

  it("an unknown scan status is refused", async () => {
    fakeApi(() => ok([{ ...DOCUMENT, status: "maybe", diff: "" }]));
    await expect(scanCorpus()).rejects.toThrow();
  });

  it("applying a document sends its new content", async () => {
    const sent = fakeApi(() => ok({ ...DOCUMENT, content: "nouveau" }));
    await applyCorpusDocument("dmpa-sc", "nouveau");
    expect(sent[0]).toMatchObject({ url: "/api/knowledge/corpus/dmpa-sc/apply", body: { content: "nouveau" } });
  });
});
