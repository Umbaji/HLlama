import { apiClient } from "./client";
import type { ApiResponse, PaginationMeta, User } from "@/lib/types/api";

interface UsersListResponse {
  data: User[];
  meta: PaginationMeta;
}

export async function fetchUsers(page: number = 1, limit: number = 10): Promise<UsersListResponse> {
  const response = await apiClient.get<ApiResponse<User[], PaginationMeta>>("/api/users", {
    params: { page, limit },
  });
  return {
    data: response.data.data,
    meta: response.data.meta!,
  };
}

export async function fetchAdmins(page: number = 1, limit: number = 10): Promise<UsersListResponse> {
  const response = await apiClient.get<ApiResponse<User[], PaginationMeta>>("/api/admins", {
    params: { page, limit },
  });
  return {
    data: response.data.data,
    meta: response.data.meta!,
  };
}

export async function deactivateUser(userId: string): Promise<void> {
  await apiClient.post(`/api/manage/users/${userId}/deactivate`);
}

export async function activateUser(userId: string): Promise<void> {
  await apiClient.post(`/api/manage/users/${userId}/activate`);
}

export async function deleteUser(userId: string): Promise<void> {
  await apiClient.delete(`/api/manage/users/${userId}`);
}

export async function promoteUser(userId: string): Promise<void> {
  await apiClient.post(`/api/manage/users/${userId}/promote`);
}

export async function demoteUser(userId: string): Promise<void> {
  await apiClient.post(`/api/manage/users/${userId}/demote`);
}
