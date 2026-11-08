"use client";

import { useLocale, useTranslations } from "next-intl";
import { Users, UserCheck, ShieldCheck, MessageSquare } from "lucide-react";
import type { OverviewStats } from "@/lib/types/api";

interface StatGridProps {
  stats: OverviewStats;
}

interface StatCardProps {
  label: string;
  value: number;
  locale: string;
  icon: React.ComponentType<{ className?: string }>;
  color: string;
}

function formatCount(value: number, locale: string): string {
  return value.toLocaleString(locale === "en" ? "en-US" : "fr-FR");
}

function StatCard({ label, value, locale, icon: Icon, color }: StatCardProps) {
  return (
    <div className="flex items-center gap-3 rounded-md border border-border bg-background px-3 py-2.5">
      <div className={`flex h-7 w-7 shrink-0 items-center justify-center rounded ${color}`}>
        <Icon className="h-3.5 w-3.5 text-white" />
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[11px] text-muted-foreground">{label}</p>
        <p className="text-base font-semibold tabular-nums leading-tight">{formatCount(value, locale)}</p>
      </div>
    </div>
  );
}

interface MiniStatProps {
  label: string;
  value: number;
  locale: string;
}

function MiniStat({ label, value, locale }: MiniStatProps) {
  return (
    <div className="flex items-center justify-between rounded border border-border/60 bg-muted/30 px-3 py-2">
      <span className="text-[11px] text-muted-foreground">{label}</span>
      <span className="text-sm font-semibold tabular-nums">{formatCount(value, locale)}</span>
    </div>
  );
}

export function StatGrid({ stats }: StatGridProps) {
  const locale = useLocale();
  const t = useTranslations("dashboard");

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <StatCard label={t("totalUsers")} value={stats.total_users} locale={locale} icon={Users} color="bg-blue-500" />
        <StatCard label={t("activeUsers")} value={stats.active_users} locale={locale} icon={UserCheck} color="bg-emerald-500" />
        <StatCard label={t("totalQuestions")} value={stats.total_questions} locale={locale} icon={MessageSquare} color="bg-amber-500" />
        <StatCard label={t("totalAdmins")} value={stats.total_admins} locale={locale} icon={ShieldCheck} color="bg-indigo-500" />
      </div>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <MiniStat label={t("newUsers7d")} value={stats.new_users_7d} locale={locale} />
        <MiniStat label={t("newUsers30d")} value={stats.new_users_30d} locale={locale} />
        <MiniStat label={t("questions7d")} value={stats.questions_7d} locale={locale} />
        <MiniStat label={t("questions30d")} value={stats.questions_30d} locale={locale} />
      </div>
    </div>
  );
}
