import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  enrollMfa,
  getCurrentUser,
  login,
  recoverMfa,
  setupMfa,
  verifyMfa,
} from "./auth";
import { fetchFeedback } from "./feedback";
import {
  deleteQuestion, downloadBlob, exportQuestionsCsv, exportUsersCsv, fetchActivityLogs, fetchAllQuestions,
} from "./management";
import { fetchOverviewStats } from "./stats";
import { activateUser, deactivateUser, deleteUser, demoteUser, fetchAdmins, fetchUsers, promoteUser } from "./users";
import { fakeApi, ok, testMeta, type SentRequest } from "@/test/fake-api";

const META = {
  ...testMeta,
  current_page: 2,
  total_pages: 5,
  total_count: 90,
  page_size: 20,
  has_more: true,
};

function sentAs(r: SentRequest | undefined) {
  return r && { method: r.method, url: r.url };
}

describe("auth", () => {
  it("logs in with the email as the username", async () => {
    const sent = fakeApi(() => ({
      status: 200,
      body: { status: 200, error: false, message: "LOGIN_SUCCESS", data: { access_token: "t", token_type: "bearer" }, meta: testMeta },
    }));
    await expect(login("admin@example.org", "secret")).resolves.toEqual({
      message: "LOGIN_SUCCESS",
      data: { access_token: "t", token_type: "bearer" },
    });
    expect(sent[0]).toMatchObject({ method: "POST", url: "/api/login", body: { username: "admin@example.org", password: "secret" } });
  });

  it("parses a pending MFA challenge without treating it as an access token", async () => {
    const challenge = { challenge_token: "c".repeat(43), expires_in_seconds: 300 };
    fakeApi(() => ({
      status: 200,
      body: { status: 200, error: false, message: "MFA_REQUIRED", data: challenge, meta: testMeta },
    }));
    await expect(login("admin@example.org", "secret")).resolves.toEqual({ message: "MFA_REQUIRED", data: challenge });
  });

  it("sends strict MFA endpoint payloads", async () => {
    const token = "c".repeat(43);
    const sent = fakeApi((request) => {
      if (request.url.endsWith("/setup")) return ok({ secret: "s".repeat(32), otpauth_uri: "otpauth://totp/x", enroll_challenge_token: token, expires_in_seconds: 300 });
      if (request.url.endsWith("/enroll")) return ok({ access_token: "t", token_type: "bearer", recovery_codes: ["A".repeat(31), ...Array.from({ length: 9 }, (_, index) => `B${index}`)] });
      return ok({ access_token: "t", token_type: "bearer" });
    });
    await setupMfa(token);
    await enrollMfa(token, "123456");
    await verifyMfa(token, "123456");
    await recoverMfa(token, "A-A-A-A-A-A");
    expect(sent.map((request) => request.url)).toEqual([
      "/api/login/mfa/setup",
      "/api/login/mfa/enroll",
      "/api/login/mfa/verify",
      "/api/login/mfa/recover",
    ]);
  });

  it("reads the signed-in user", async () => {
    const sent = fakeApi(() => ok({ id: "u1" }));
    await expect(getCurrentUser()).resolves.toEqual({ id: "u1" });
    expect(sentAs(sent[0])).toEqual({ method: "GET", url: "/api/users/me/" });
  });
});

describe("lists come back with their page", () => {
  it.each([
    ["users", () => fetchUsers(2, 20), "/api/users"],
    ["admins", () => fetchAdmins(2, 20), "/api/admins"],
    ["questions", () => fetchAllQuestions(2, 20), "/api/manage/questions"],
    ["logs", () => fetchActivityLogs(2, 20), "/api/manage/logs"],
  ])("%s", async (_name, call, url) => {
    const sent = fakeApi(() => ok([{ id: "a" }], META));
    await expect(call()).resolves.toEqual({ data: [{ id: "a" }], meta: META });
    expect(sent[0]).toMatchObject({ method: "GET", url, params: { page: 2, limit: 20 } });
  });

  it("feedback, filtered by question", async () => {
    const sent = fakeApi(() => ok({ items: [], aggregates: [] }, META));
    await expect(fetchFeedback(1, 20, "useful")).resolves.toEqual({ items: [], aggregates: [], meta: META });
    expect(sent[0]?.params).toEqual({ page: 1, limit: 20, question_key: "useful" });
  });
});

describe("actions on one record go to that record", () => {
  it.each([
    ["deactivate", () => deactivateUser("u1"), "POST", "/api/manage/users/u1/deactivate"],
    ["activate", () => activateUser("u1"), "POST", "/api/manage/users/u1/activate"],
    ["promote", () => promoteUser("u1"), "POST", "/api/manage/users/u1/promote"],
    ["demote", () => demoteUser("u1"), "POST", "/api/manage/users/u1/demote"],
    ["delete a user", () => deleteUser("u1"), "DELETE", "/api/manage/users/u1"],
    ["delete a question", () => deleteQuestion("q1"), "DELETE", "/api/manage/questions/q1"],
  ])("%s", async (_name, call, method, url) => {
    const sent = fakeApi();
    await call();
    expect(sentAs(sent[0])).toEqual({ method, url });
  });
});

describe("statistics", () => {
  it("overview", async () => {
    const sent = fakeApi(() => ok({ value: 1 }));
    await expect(fetchOverviewStats()).resolves.toEqual({ value: 1 });
    expect(sent[0]).toMatchObject({ method: "GET", url: "/api/stats/overview" });
    expect(sent[0]?.params).toEqual(undefined);
  });
});

describe("CSV exports", () => {
  let click: ReturnType<typeof vi.fn>;
  beforeEach(() => {
    URL.createObjectURL = vi.fn(() => "blob:export");
    URL.revokeObjectURL = vi.fn();
    click = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(click);
  });
  afterEach(() => vi.restoreAllMocks());

  it("downloads the blob under the given name, then releases it", () => {
    let name = "";
    click.mockImplementation(function (this: HTMLAnchorElement) { name = this.download; });
    downloadBlob(new Blob(["a,b"]), "file.csv");
    expect(name).toBe("file.csv");
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:export");
    expect(document.querySelector("a")).toBeNull();
  });

  it.each([
    ["users", exportUsersCsv, "/api/manage/export/users"],
    ["questions", exportQuestionsCsv, "/api/manage/export/questions"],
  ])("%s", async (_name, call, url) => {
    const sent = fakeApi(() => ({ status: 200, body: new Blob(["a,b"]) }));
    await call();
    expect(sentAs(sent[0])).toEqual({ method: "GET", url });
    expect(click).toHaveBeenCalledOnce();
  });
});
