import { z } from "zod";
import { apiClient } from "@/lib/api/client";
import type { ApiJsonValue, ApiResponse } from "@/lib/types/api";
import {
  corpusDocumentDetailSchema,
  corpusDocumentSchema,
  corpusScanSchema,
  type CorpusDocument,
  type CorpusDocumentDetail,
  type CorpusScan,
} from "../types/knowledge";

export async function fetchCorpus(): Promise<CorpusDocument[]> {
  const response = await apiClient.get<ApiResponse<ApiJsonValue>>("/api/knowledge/corpus");
  return z.array(corpusDocumentSchema).parse(response.data.data);
}

export async function fetchCorpusDocument(slug: string): Promise<CorpusDocumentDetail> {
  const response = await apiClient.get<ApiResponse<ApiJsonValue>>(`/api/knowledge/corpus/${slug}`);
  return corpusDocumentDetailSchema.parse(response.data.data);
}

export async function scanCorpus(): Promise<CorpusScan[]> {
  const response = await apiClient.post<ApiResponse<ApiJsonValue>>("/api/knowledge/corpus/scan");
  return z.array(corpusScanSchema).parse(response.data.data);
}

export async function applyCorpusDocument(slug: string, content: string): Promise<CorpusDocumentDetail> {
  const response = await apiClient.post<ApiResponse<ApiJsonValue>>(`/api/knowledge/corpus/${slug}/apply`, { content });
  return corpusDocumentDetailSchema.parse(response.data.data);
}
