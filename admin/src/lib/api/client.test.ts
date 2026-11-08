import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./client";
import { fetchOverviewStats } from "./stats";
import { fakeApi, ok, testMeta } from "@/test/fake-api";

afterEach(() => localStorage.clear());

describe("apiClient", () => {
  it("sends the stored token as a bearer token", async () => {
    localStorage.setItem("admin_token", "the-token");
    const sent = fakeApi(() => ok({}));
    await fetchOverviewStats();
    expect(sent[0]?.headers.get("Authorization")).toBe("Bearer the-token");
  });

  it("sends no Authorization header without a token", async () => {
    const sent = fakeApi(() => ok({}));
    await fetchOverviewStats();
    expect(sent[0]?.headers.has("Authorization")).toBe(false);
  });

  it("rejects a body whose HTTP status does not match its envelope", async () => {
    fakeApi(() => ({ status: 200, body: { status: 409, error: true, message: "ALREADY_EXISTS", data: null, meta: testMeta } }));
    const failure = await fetchOverviewStats().catch((e: unknown) => e);
    expect(failure).toBeInstanceOf(ApiError);
    expect(failure).toMatchObject({ code: "INVALID_API_RESPONSE", status: 200 });
  });

  it("keeps the backend's message and status on an HTTP error", async () => {
    fakeApi(() => ({ status: 403, body: { status: 403, error: true, message: "FORBIDDEN", data: null, meta: testMeta } }));
    await expect(fetchOverviewStats()).rejects.toMatchObject({ code: "FORBIDDEN", status: 403 });
  });

  it("calls an answer without a body a server error", async () => {
    fakeApi(() => ({ status: 502, body: undefined }));
    await expect(fetchOverviewStats()).rejects.toMatchObject({ code: "SERVER_ERROR", status: 502 });
  });

  it("rejects a success response that violates the shared envelope", async () => {
    fakeApi(() => ({ status: 200, body: { status: 200, error: false, message: "OK", data: {}, meta: null } }));
    await expect(fetchOverviewStats()).rejects.toMatchObject({
      code: "INVALID_API_RESPONSE",
      status: 200,
    });
  });

  it("forgets the token and goes to the login page when the backend answers 401", async () => {
    // jsdom cannot navigate: it reports the attempt on console.error, which
    // is the proof that the redirect was asked for.
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    localStorage.setItem("admin_token", "expired");
    fakeApi(() => ({ status: 401, body: { status: 401, error: true, message: "UNAUTHORIZED", data: null, meta: testMeta } }));
    await expect(fetchOverviewStats()).rejects.toMatchObject({ status: 401 });
    expect(localStorage.getItem("admin_token")).toBeNull();
    expect(String(consoleError.mock.calls[0]?.[0])).toContain("navigation");
    consoleError.mockRestore();
  });

  it("keeps the pending MFA screen when a challenge code is rejected", async () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    localStorage.removeItem("admin_token");
    fakeApi(() => ({ status: 401, body: { status: 401, error: true, message: "MFA_INVALID", data: null, meta: testMeta } }));
    await expect(fetchOverviewStats()).rejects.toMatchObject({ code: "MFA_INVALID", status: 401 });
    expect(localStorage.getItem("admin_token")).toBeNull();
    expect(consoleError).not.toHaveBeenCalled();
    consoleError.mockRestore();
  });
});
