"use client";

import { useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { fetchOverviewStats } from "@/lib/api/stats";
import { StatGrid } from "@/components/charts/stat-grid";

export default function OverviewPage() {
  const t = useTranslations("dashboard");

  const { data: stats } = useQuery({
    queryKey: ["stats-overview"],
    queryFn: fetchOverviewStats,
  });

  return (
    <div className="space-y-4">
      <h1 className="text-base font-semibold">{t("title")}</h1>

      {stats && <StatGrid stats={stats} />}
    </div>
  );
}
