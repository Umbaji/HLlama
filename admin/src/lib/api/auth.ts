import { apiClient } from "./client";
import { z } from "zod";
import { ApiError } from "./client";
import type {
  ApiJsonValue,
  ApiResponse,
  LoginResponse,
  MfaEnrollmentResponse,
  MfaSetupResponse,
  User,
} from "@/lib/types/api";

const tokenSchema = z.strictObject({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
});
const challengeSchema = z.strictObject({
  challenge_token: z.string().min(32).max(256),
  expires_in_seconds: z.number().int().min(1).max(300),
});
const loginResultSchema = z.discriminatedUnion("message", [
  z.strictObject({ message: z.literal("LOGIN_SUCCESS"), data: tokenSchema }),
  z.strictObject({ message: z.literal("MFA_REQUIRED"), data: challengeSchema }),
  z.strictObject({ message: z.literal("MFA_SETUP_REQUIRED"), data: challengeSchema }),
]);
export type LoginResult = z.infer<typeof loginResultSchema>;
const setupResponseSchema = z.strictObject({
  secret: z.string().length(32),
  otpauth_uri: z.string().min(1).max(1024),
  enroll_challenge_token: z.string().min(32).max(256),
  expires_in_seconds: z.number().int().min(1).max(300),
});
const enrollmentResponseSchema = tokenSchema.extend({
  recovery_codes: z.array(z.string()).length(10),
});

async function postMfa<T>(
  path: string,
  body: Record<string, string>,
  schema: z.ZodType<T>,
): Promise<T> {
  const response = await apiClient.post<ApiResponse<ApiJsonValue>>(path, body);
  const parsed = schema.safeParse(response.data.data);
  if (!parsed.success) throw new ApiError("INVALID_API_RESPONSE", response.status);
  return parsed.data;
}

export async function login(email: string, password: string): Promise<LoginResult> {
  const response = await apiClient.post<ApiResponse<ApiJsonValue>>("/api/login", {
    username: email,
    password,
  });
  const parsed = loginResultSchema.safeParse({
    message: response.data.message,
    data: response.data.data,
  });
  if (!parsed.success) throw new ApiError("INVALID_API_RESPONSE", response.status);
  return parsed.data;
}

export function setupMfa(setupChallengeToken: string): Promise<MfaSetupResponse> {
  return postMfa("/api/login/mfa/setup", { setup_challenge_token: setupChallengeToken }, setupResponseSchema);
}

export function enrollMfa(
  enrollChallengeToken: string,
  code: string,
): Promise<MfaEnrollmentResponse> {
  return postMfa(
    "/api/login/mfa/enroll",
    { enroll_challenge_token: enrollChallengeToken, code },
    enrollmentResponseSchema,
  );
}

export function verifyMfa(challengeToken: string, code: string): Promise<LoginResponse> {
  return postMfa("/api/login/mfa/verify", { challenge_token: challengeToken, code }, tokenSchema);
}

export function recoverMfa(
  challengeToken: string,
  recoveryCode: string,
): Promise<LoginResponse> {
  return postMfa(
    "/api/login/mfa/recover",
    { challenge_token: challengeToken, recovery_code: recoveryCode },
    tokenSchema,
  );
}

export async function getCurrentUser(): Promise<User> {
  const response = await apiClient.get<ApiResponse<User>>("/api/users/me/");
  return response.data.data;
}
