import axios, { type AxiosError, type InternalAxiosRequestConfig } from "axios";
import { z } from "zod";
import type { ApiJsonValue, ApiResponse } from "@/lib/types/api";

const API_BASE_URL = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:8000";
const apiResponseSchema = z
  .strictObject({
    status: z.number().int().min(100).max(599),
    error: z.boolean(),
    message: z.string().regex(/^[A-Z][A-Z0-9_]*$/),
    data: z.json(),
    meta: z
      .object({
        request_id: z.uuid(),
        served_at: z.iso.datetime(),
      })
      .catchall(z.json()),
  })
  .superRefine((body, context) => {
    if (body.error !== (body.status >= 400)) {
      context.addIssue({ code: "custom", message: "Invalid response outcome" });
    }
    if (body.error && body.data !== null) {
      context.addIssue({ code: "custom", message: "Error data must be null" });
    }
  });

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("admin_token");
    if (token && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => {
    if (response.config.responseType === "blob") return response;

    const parsed = apiResponseSchema.safeParse(response.data);
    if (!parsed.success || parsed.data.status !== response.status) {
      return Promise.reject(new ApiError("INVALID_API_RESPONSE", response.status));
    }
    if (parsed.data.error) {
      return Promise.reject(new ApiError(parsed.data.message, parsed.data.status));
    }
    return { ...response, data: parsed.data };
  },
  (error: AxiosError<ApiResponse<ApiJsonValue>>) => {
    const status = error.response?.status ?? 500;
    const parsed = apiResponseSchema.safeParse(error.response?.data);
    const message =
      parsed.success && parsed.data.error && parsed.data.status === status
        ? parsed.data.message
        : "SERVER_ERROR";

    if (status === 401 && typeof window !== "undefined" && localStorage.getItem("admin_token")) {
      localStorage.removeItem("admin_token");
      const locale = window.location.pathname.split("/")[1] ?? "fr";
      window.location.replace(new URL(`/${locale}/login`, window.location.origin));
    }

    return Promise.reject(new ApiError(message, status));
  }
);

export class ApiError extends Error {
  status: number;
  code: string;

  constructor(code: string, status: number) {
    super(code);
    this.code = code;
    this.status = status;
    this.name = "ApiError";
  }
}
