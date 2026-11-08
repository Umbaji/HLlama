import { z } from "zod";

export const corpusDocumentSchema = z.strictObject({
  slug: z.string(),
  title: z.string(),
  source: z.string(),
  source_url: z.string(),
  published: z.string(),
  language: z.string(),
  characters: z.number().int().nonnegative(),
  passages: z.number().int().nonnegative(),
});

export const corpusDocumentDetailSchema = corpusDocumentSchema.extend({
  content: z.string(),
});

export const corpusScanSchema = corpusDocumentSchema.extend({
  new_content: z.string().optional(),
  status: z.enum(["unchanged", "changed", "new", "unreachable", "unreadable", "no_source"]),
  diff: z.string(),
  error: z.string().optional(),
});

export type CorpusDocument = z.infer<typeof corpusDocumentSchema>;
export type CorpusDocumentDetail = z.infer<typeof corpusDocumentDetailSchema>;
export type CorpusScan = z.infer<typeof corpusScanSchema>;
