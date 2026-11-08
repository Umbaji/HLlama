import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from "axios";
import { apiClient } from "@/lib/api/client";
import type { ApiMetadata } from "@/lib/types/api";

export const testMeta: ApiMetadata = {
  request_id: "550e8400-e29b-41d4-a716-446655440000",
  served_at: "2026-10-29T12:00:00Z",
};

/** One request the code under test sent, as the API would have received it. */
export interface SentRequest {
  method: string;
  url: string;
  params: Record<string, unknown> | undefined;
  body: unknown;
  headers: AxiosHeaders;
}

export interface Reply {
  status: number;
  body: unknown;
}

/** The backend's envelope around a successful answer. */
export function ok(data: unknown, meta: ApiMetadata = testMeta): Reply {
  return { status: 200, body: { status: 200, error: false, message: "OK", data, meta } };
}

/**
 * Replaces the network under apiClient: every request goes through the real
 * interceptors, then to `answer` instead of the backend. Returns the list
 * of what was sent.
 */
export function fakeApi(answer: (request: SentRequest) => Reply = () => ok(null)): SentRequest[] {
  const sent: SentRequest[] = [];
  apiClient.defaults.adapter = async (config: InternalAxiosRequestConfig) => {
    const request: SentRequest = {
      method: (config.method ?? "get").toUpperCase(),
      url: config.url ?? "",
      params: config.params as Record<string, unknown> | undefined,
      body: typeof config.data === "string" ? JSON.parse(config.data) : config.data,
      headers: AxiosHeaders.from(config.headers),
    };
    sent.push(request);
    const { status, body } = answer(request);
    const response = { data: body, status, statusText: String(status), headers: {}, config };
    if (status >= 400) {
      throw new AxiosError(`status ${status}`, String(status), config, null, response);
    }
    return response;
  };
  return sent;
}
