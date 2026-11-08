"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { getCurrentUser } from "@/lib/api/auth";
import { exportUsersCsv, exportQuestionsCsv } from "@/lib/api/management";
import {
  Shield,
  User,
  Server,
  Database,
  Bell,
  AlertTriangle,
  Download,
  Check,
  Circle,
} from "lucide-react";

export default function SettingsPage() {
  const t = useTranslations("settings");

  const { data: user } = useQuery({
    queryKey: ["current-user"],
    queryFn: getCurrentUser,
  });

  const [passwords, setPasswords] = useState({
    current: "",
    newPwd: "",
    confirm: "",
  });
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordSuccess, setPasswordSuccess] = useState(false);

  const [notifications, setNotifications] = useState({
    newUser: true,
    newQuestion: false,
  });

  const [exporting, setExporting] = useState<"users" | "questions" | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);

  const handlePasswordChange = () => {
    setPasswordError(null);
    setPasswordSuccess(false);
    if (passwords.newPwd !== passwords.confirm) {
      setPasswordError(t("passwordMismatch"));
      return;
    }
    setPasswordSuccess(true);
    setPasswords({ current: "", newPwd: "", confirm: "" });
  };

  const handleExport = async (type: "users" | "questions") => {
    setExporting(type);
    setExportError(null);
    try {
      if (type === "users") {
        await exportUsersCsv();
      } else {
        await exportQuestionsCsv();
      }
    } catch {
      setExportError("Export failed");
    } finally {
      setExporting(null);
    }
  };

  const apiUrl = process.env["NEXT_PUBLIC_API_URL"] ?? "http://localhost:8000";

  return (
    <div className="space-y-4">
      <h1 className="text-base font-semibold">{t("title")}</h1>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Profile */}
        <section className="rounded-md border border-border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <User className="h-3.5 w-3.5 text-blue-500" />
            <h2 className="text-sm font-semibold">{t("profile")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("profileDesc")}</p>
          <div className="space-y-2.5">
            <div>
              <label className="text-[11px] font-medium text-muted-foreground">{t("adminName")}</label>
              <p className="mt-0.5 text-sm font-medium">{user?.fullname ?? "—"}</p>
            </div>
            <div>
              <label className="text-[11px] font-medium text-muted-foreground">{t("adminEmail")}</label>
              <p className="mt-0.5 text-sm font-medium">{user?.email ?? "—"}</p>
            </div>
          </div>
        </section>

        {/* Security */}
        <section className="rounded-md border border-border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Shield className="h-3.5 w-3.5 text-emerald-500" />
            <h2 className="text-sm font-semibold">{t("security")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("securityDesc")}</p>
          <div className="space-y-2">
            <input
              type="password"
              placeholder={t("currentPassword")}
              value={passwords.current}
              onChange={(e) => setPasswords((p) => ({ ...p, current: e.target.value }))}
              className="w-full rounded border border-border bg-muted/30 px-3 py-1.5 text-xs outline-none focus:border-primary"
            />
            <input
              type="password"
              placeholder={t("newPassword")}
              value={passwords.newPwd}
              onChange={(e) => setPasswords((p) => ({ ...p, newPwd: e.target.value }))}
              className="w-full rounded border border-border bg-muted/30 px-3 py-1.5 text-xs outline-none focus:border-primary"
            />
            <input
              type="password"
              placeholder={t("confirmPassword")}
              value={passwords.confirm}
              onChange={(e) => setPasswords((p) => ({ ...p, confirm: e.target.value }))}
              className="w-full rounded border border-border bg-muted/30 px-3 py-1.5 text-xs outline-none focus:border-primary"
            />
            {passwordError && <p className="text-[11px] text-red-500">{passwordError}</p>}
            {passwordSuccess && (
              <p className="flex items-center gap-1 text-[11px] text-emerald-600">
                <Check className="h-3 w-3" />
                {t("passwordChanged")}
              </p>
            )}
            <button
              onClick={handlePasswordChange}
              disabled={!passwords.current || !passwords.newPwd || !passwords.confirm}
              className="mt-1 rounded bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground transition-opacity disabled:opacity-40"
            >
              {t("changePassword")}
            </button>
          </div>
        </section>

        {/* System */}
        <section className="rounded-md border border-border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Server className="h-3.5 w-3.5 text-indigo-500" />
            <h2 className="text-sm font-semibold">{t("system")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("systemDesc")}</p>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("apiUrl")}</span>
              <code className="text-[11px] font-mono text-foreground">{apiUrl}</code>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("appVersion")}</span>
              <span className="text-[11px] font-medium">2.0.0</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-[11px] text-muted-foreground">{t("status")}</span>
              <span className="flex items-center gap-1 text-[11px] font-medium text-emerald-600">
                <Circle className="h-2 w-2 fill-emerald-500 text-emerald-500" />
                {t("online")}
              </span>
            </div>
          </div>
        </section>

        {/* Data Management */}
        <section className="rounded-md border border-border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Database className="h-3.5 w-3.5 text-amber-500" />
            <h2 className="text-sm font-semibold">{t("dataManagement")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("dataManagementDesc")}</p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => handleExport("users")}
              disabled={exporting === "users"}
              className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
            >
              <Download className="h-3 w-3" />
              {exporting === "users" ? t("exporting") : t("exportUsers")}
            </button>
            <button
              onClick={() => handleExport("questions")}
              disabled={exporting === "questions"}
              className="flex items-center gap-1.5 rounded border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
            >
              <Download className="h-3 w-3" />
              {exporting === "questions" ? t("exporting") : t("exportQuestions")}
            </button>
          </div>
          {exportError && <p className="mt-2 text-[11px] text-red-500">{exportError}</p>}
        </section>

        {/* Notifications */}
        <section className="rounded-md border border-border bg-background p-4">
          <div className="mb-3 flex items-center gap-2">
            <Bell className="h-3.5 w-3.5 text-purple-500" />
            <h2 className="text-sm font-semibold">{t("notifications")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("notificationsDesc")}</p>
          <div className="space-y-2.5">
            <label className="flex cursor-pointer items-center justify-between">
              <span className="text-xs">{t("notifyNewUser")}</span>
              <button
                type="button"
                role="switch"
                aria-checked={notifications.newUser}
                onClick={() => setNotifications((n) => ({ ...n, newUser: !n.newUser }))}
                className={`relative h-5 w-9 rounded-full transition-colors ${
                  notifications.newUser ? "bg-primary" : "bg-muted"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    notifications.newUser ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </label>
            <label className="flex cursor-pointer items-center justify-between">
              <span className="text-xs">{t("notifyNewQuestion")}</span>
              <button
                type="button"
                role="switch"
                aria-checked={notifications.newQuestion}
                onClick={() => setNotifications((n) => ({ ...n, newQuestion: !n.newQuestion }))}
                className={`relative h-5 w-9 rounded-full transition-colors ${
                  notifications.newQuestion ? "bg-primary" : "bg-muted"
                }`}
              >
                <span
                  className={`absolute top-0.5 left-0.5 h-4 w-4 rounded-full bg-white shadow transition-transform ${
                    notifications.newQuestion ? "translate-x-4" : "translate-x-0"
                  }`}
                />
              </button>
            </label>
          </div>
        </section>

        {/* Danger Zone */}
        <section className="rounded-md border border-red-200 bg-red-50/30 p-4">
          <div className="mb-3 flex items-center gap-2">
            <AlertTriangle className="h-3.5 w-3.5 text-red-500" />
            <h2 className="text-sm font-semibold text-red-700">{t("dangerZone")}</h2>
          </div>
          <p className="mb-3 text-[11px] text-muted-foreground">{t("dangerZoneDesc")}</p>
          <button
            disabled
            title={t("comingSoon")}
            className="rounded border border-red-200 bg-white px-3 py-1.5 text-xs font-medium text-red-600 opacity-50"
          >
            {t("clearLogs")}
          </button>
          <p className="mt-1.5 text-[10px] italic text-muted-foreground">{t("comingSoon")}</p>
        </section>
      </div>
    </div>
  );
}
