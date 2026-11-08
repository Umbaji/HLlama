import { apiClient } from "./client";
import type { ApiResponse, OverviewStats } from "@/lib/types/api";

export async function fetchOverviewStats(): Promise<OverviewStats> {
  const response = await apiClient.get<ApiResponse<OverviewStats>>("/api/stats/overview");
  return response.data.data;
}
