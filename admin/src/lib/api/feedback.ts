import { apiClient } from "./client";
import type { ApiResponse, FeedbackPage, PaginationMeta } from "@/lib/types/api";

export async function fetchFeedback(
  page: number = 1,
  limit: number = 20,
  questionKey?: string
): Promise<FeedbackPage & { meta: PaginationMeta }> {
  const response = await apiClient.get<ApiResponse<FeedbackPage, PaginationMeta>>("/api/manage/feedback", {
    params: { page, limit, question_key: questionKey },
  });
  return { ...response.data.data, meta: response.data.meta! };
}
