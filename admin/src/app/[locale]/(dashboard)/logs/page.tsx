"use client";

import { useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { fetchActivityLogs } from "@/lib/api/management";
import { formatDateTime } from "@/lib/utils/format";

export default function LogsPage() {
  const t = useTranslations("logs");
  const tc = useTranslations("common");
  const locale = useLocale();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["logs", page],
    queryFn: () => fetchActivityLogs(page, 20),
  });

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>;
  }

  const logs = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("title")}</h1>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("action")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("admin")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("target")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("details")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("date")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {logs.map((log) => (
              <tr key={log.id} className="hover:bg-muted/30">
                <td className="px-3 py-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[10px]">{log.action}</span>
                </td>
                <td className="px-3 py-2 text-muted-foreground">{log.admin_name ?? "—"}</td>
                <td className="px-3 py-2 text-muted-foreground">
                  <span className="text-[10px]">{log.target_type}</span>
                  {log.target_id && <span className="ml-1 font-mono text-[10px]">{log.target_id.slice(0, 8)}</span>}
                </td>
                <td className="max-w-xs truncate px-3 py-2 text-muted-foreground">{log.details ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{formatDateTime(log.created_at, locale)}</td>
              </tr>
            ))}
            {logs.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">{t("noLogs")}</td></tr>
            )}
          </tbody>
        </table>
      </div>

      {meta && meta.total_pages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{tc("page")} {meta.current_page} {tc("of")} {meta.total_pages}</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40">{tc("previous")}</button>
            <button disabled={!meta.has_more} onClick={() => setPage(page + 1)} className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40">{tc("next")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
