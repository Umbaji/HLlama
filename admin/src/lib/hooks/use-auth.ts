"use client";

import { useState, useCallback } from "react";
import { useRouter } from "@/i18n/navigation";
import {
  enrollMfa,
  getCurrentUser,
  login as loginApi,
  recoverMfa,
  setupMfa,
  verifyMfa,
} from "@/lib/api/auth";
import { ApiError } from "@/lib/api/client";
import type { LoginResponse, User } from "@/lib/types/api";

export type MfaStage =
  | { kind: "none" }
  | { kind: "verify" | "recover"; challengeToken: string }
  | { kind: "enroll"; challengeToken: string; secret: string; otpauthUri: string }
  | { kind: "recovery-codes"; codes: string[] };

interface AuthState {
  user: User | null;
  isLoading: boolean;
  error: string | null;
  mfa: MfaStage;
}

const initialState: AuthState = {
  user: null,
  isLoading: false,
  error: null,
  mfa: { kind: "none" },
};

export function useAuth() {
  const router = useRouter();
  const [state, setState] = useState<AuthState>(initialState);

  const fail = useCallback((error: unknown) => {
    const code = error instanceof ApiError ? error.code : "SERVER_ERROR";
    setState((current) => ({ ...current, isLoading: false, error: code }));
  }, []);

  const finishLogin = useCallback(async (result: LoginResponse) => {
    localStorage.setItem("admin_token", result.access_token);
    const user = await getCurrentUser();
    if (!user.is_admin) {
      localStorage.removeItem("admin_token");
      throw new ApiError("UNAUTHORIZED_ACCESS", 403);
    }
    setState({ ...initialState, user });
    router.push("/overview");
  }, [router]);

  const login = useCallback(async (email: string, password: string) => {
    localStorage.removeItem("admin_token");
    setState({ ...initialState, isLoading: true });
    try {
      const result = await loginApi(email, password);
      if (result.message === "LOGIN_SUCCESS") {
        await finishLogin(result.data);
      } else if (result.message === "MFA_REQUIRED") {
        setState({ ...initialState, mfa: { kind: "verify", challengeToken: result.data.challenge_token } });
      } else {
        const setup = await setupMfa(result.data.challenge_token);
        setState({
          ...initialState,
          mfa: {
            kind: "enroll",
            challengeToken: setup.enroll_challenge_token,
            secret: setup.secret,
            otpauthUri: setup.otpauth_uri,
          },
        });
      }
    } catch (error) {
      fail(error);
    }
  }, [fail, finishLogin]);

  const verify = useCallback(async (code: string) => {
    if (state.mfa.kind !== "verify") return;
    setState((current) => ({ ...current, isLoading: true, error: null }));
    try {
      await finishLogin(await verifyMfa(state.mfa.challengeToken, code));
    } catch (error) {
      fail(error);
    }
  }, [fail, finishLogin, state.mfa]);

  const recover = useCallback(async (code: string) => {
    if (state.mfa.kind !== "recover") return;
    setState((current) => ({ ...current, isLoading: true, error: null }));
    try {
      await finishLogin(await recoverMfa(state.mfa.challengeToken, code));
    } catch (error) {
      fail(error);
    }
  }, [fail, finishLogin, state.mfa]);

  const enroll = useCallback(async (code: string) => {
    if (state.mfa.kind !== "enroll") return;
    setState((current) => ({ ...current, isLoading: true, error: null }));
    try {
      const result = await enrollMfa(state.mfa.challengeToken, code);
      localStorage.setItem("admin_token", result.access_token);
      setState({ ...initialState, mfa: { kind: "recovery-codes", codes: result.recovery_codes } });
    } catch (error) {
      fail(error);
    }
  }, [fail, state.mfa]);

  const beginRecovery = useCallback(() => {
    if (state.mfa.kind === "verify") {
      setState({ ...initialState, mfa: { kind: "recover", challengeToken: state.mfa.challengeToken } });
    }
  }, [state.mfa]);

  const finishEnrollment = useCallback(async () => {
    if (state.mfa.kind !== "recovery-codes") return;
    setState((current) => ({ ...current, isLoading: true, error: null }));
    try {
      const user = await getCurrentUser();
      setState({ ...initialState, user });
      router.push("/overview");
    } catch (error) {
      fail(error);
    }
  }, [fail, router, state.mfa]);

  const logout = useCallback(() => {
    localStorage.removeItem("admin_token");
    setState(initialState);
    router.push("/login");
  }, [router]);

  const checkAuth = useCallback(async () => {
    if (!localStorage.getItem("admin_token")) {
      router.push("/login");
      return;
    }
    setState((current) => ({ ...current, isLoading: true }));
    try {
      const user = await getCurrentUser();
      if (!user.is_admin) throw new ApiError("UNAUTHORIZED_ACCESS", 403);
      setState({ ...initialState, user });
    } catch {
      localStorage.removeItem("admin_token");
      router.push("/login");
    }
  }, [router]);

  return { ...state, login, verify, recover, enroll, beginRecovery, finishEnrollment, logout, checkAuth };
}
