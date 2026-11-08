"use client";

import { useState, type FormEvent } from "react";
import { useTranslations } from "next-intl";
import { useAuth } from "@/lib/hooks/use-auth";

const fieldClass = "flex h-10 w-full rounded-lg border border-input bg-transparent px-3.5 text-sm focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20";

export default function LoginPage() {
  const t = useTranslations("auth");
  const auth = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const stage = auth.mfa.kind;

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (stage === "none") void auth.login(email, password);
    if (stage === "verify") void auth.verify(code);
    if (stage === "recover") void auth.recover(code);
    if (stage === "enroll") void auth.enroll(code);
  }

  return (
    <main className="flex min-h-screen">
      <aside className="hidden w-1/2 items-center justify-center bg-zinc-900 lg:flex">
        <div className="space-y-3 px-12 text-center">
          <h1 className="text-2xl font-semibold text-white">HLlama</h1>
          <p className="text-sm text-zinc-400">{t("subtitle")}</p>
        </div>
      </aside>
      <section className="flex w-full items-center justify-center px-6 lg:w-1/2">
        <div className="w-full max-w-sm">
          <header className="mb-8 space-y-1">
            <h2 className="text-xl font-semibold">
              {stage === "none" ? t("title") : t(stage === "enroll" ? "mfaSetupTitle" : stage === "recovery-codes" ? "mfaRecoveryCodes" : "mfaTitle")}
            </h2>
            <p className="text-sm text-muted-foreground">
              {stage === "none" ? t("subtitle") : stage === "enroll" ? t("mfaSetupInstructions") : stage === "recovery-codes" ? t("mfaSaveCodes") : t("mfaSubtitle")}
            </p>
          </header>

          {stage === "recovery-codes" ? (
            <div className="space-y-5">
              <ul className="grid grid-cols-2 gap-2 rounded-md border p-4 font-mono text-sm" aria-label={t("mfaRecoveryCodes")}>
                {auth.mfa.codes.map((recoveryCode) => <li key={recoveryCode}>{recoveryCode}</li>)}
              </ul>
              <button className={`${fieldClass} justify-center bg-primary font-medium text-primary-foreground`} disabled={auth.isLoading} onClick={() => void auth.finishEnrollment()}>
                {t("mfaContinue")}
              </button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5">
              {stage === "none" && <LoginCredentials t={t} email={email} setEmail={setEmail} password={password} setPassword={setPassword} />}
              {stage === "enroll" && auth.mfa.kind === "enroll" && (
                <div className="space-y-3 rounded-md border p-4 text-sm">
                  <a className="text-primary underline" href={auth.mfa.otpauthUri}>{t("mfaOpenAuthenticator")}</a>
                  <p className="font-mono break-all">{auth.mfa.secret}</p>
                </div>
              )}
              {(stage === "verify" || stage === "enroll") && (
                <label className="block space-y-1.5 text-xs font-medium uppercase text-muted-foreground">
                  {t("mfaCode")}
                  <input className={fieldClass} value={code} onChange={(event) => setCode(event.target.value)} inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required />
                </label>
              )}
              {stage === "recover" && (
                <label className="block space-y-1.5 text-xs font-medium uppercase text-muted-foreground">
                  {t("mfaRecoveryCode")}
                  <input className={fieldClass} value={code} onChange={(event) => setCode(event.target.value.toUpperCase())} autoComplete="off" pattern="[A-Z2-7]{5}(-[A-Z2-7]{5}){4}-[A-Z2-7]" maxLength={31} required />
                </label>
              )}
              {auth.error && <p role="alert" className="rounded-md border border-destructive/20 bg-destructive/5 px-3.5 py-2.5 text-xs text-destructive">{stage === "none" ? t("error") : t("mfaError")}</p>}
              <button className={`${fieldClass} justify-center bg-primary font-medium text-primary-foreground disabled:opacity-50`} type="submit" disabled={auth.isLoading}>
                {auth.isLoading ? t("loading") : stage === "none" ? t("submit") : stage === "enroll" ? t("mfaEnable") : t("mfaVerify")}
              </button>
              {stage === "verify" && <button className="w-full text-sm text-primary underline" type="button" onClick={auth.beginRecovery}>{t("mfaUseRecovery")}</button>}
            </form>
          )}
        </div>
      </section>
    </main>
  );
}

interface LoginCredentialsProps {
  t: ReturnType<typeof useTranslations>;
  email: string;
  setEmail: (value: string) => void;
  password: string;
  setPassword: (value: string) => void;
}

function LoginCredentials({ t, email, setEmail, password, setPassword }: LoginCredentialsProps) {
  return (
    <>
      <label className="block space-y-1.5 text-xs font-medium uppercase text-muted-foreground">
        {t("email")}
        <input className={fieldClass} type="email" value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" required />
      </label>
      <label className="block space-y-1.5 text-xs font-medium uppercase text-muted-foreground">
        {t("password")}
        <input className={fieldClass} type="password" value={password} onChange={(event) => setPassword(event.target.value)} autoComplete="current-password" required />
      </label>
    </>
  );
}
