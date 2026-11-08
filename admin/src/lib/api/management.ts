import { apiClient } from "./client";
import type { ApiResponse, PaginationMeta, Question, ActivityLog } from "@/lib/types/api";

interface QuestionsListResponse {
  data: Question[];
  meta: PaginationMeta;
}

interface LogsListResponse {
  data: ActivityLog[];
  meta: PaginationMeta;
}

export async function fetchAllQuestions(page: number = 1, limit: number = 20): Promise<QuestionsListResponse> {
  const response = await apiClient.get<ApiResponse<Question[], PaginationMeta>>("/api/manage/questions", {
    params: { page, limit },
  });
  return {
    data: response.data.data,
    meta: response.data.meta!,
  };
}

export async function deleteQuestion(questionId: string): Promise<void> {
  await apiClient.delete(`/api/manage/questions/${questionId}`);
}

export async function fetchActivityLogs(page: number = 1, limit: number = 20): Promise<LogsListResponse> {
  const response = await apiClient.get<ApiResponse<ActivityLog[], PaginationMeta>>("/api/manage/logs", {
    params: { page, limit },
  });
  return {
    data: response.data.data,
    meta: response.data.meta!,
  };
}

export async function exportUsersCsv(): Promise<void> {
  const response = await apiClient.get<Blob>("/api/manage/export/users", {
    responseType: "blob",
  });
  downloadBlob(response.data, "users_export.csv");
}

export async function exportQuestionsCsv(): Promise<void> {
  const response = await apiClient.get<Blob>("/api/manage/export/questions", {
    responseType: "blob",
  });
  downloadBlob(response.data, "questions_export.csv");
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
