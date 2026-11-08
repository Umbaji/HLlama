"use client";

import { useState } from "react";
import { useTranslations, useLocale } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchAllQuestions, deleteQuestion } from "@/lib/api/management";
import { formatDateTime } from "@/lib/utils/format";
import { Trash2 } from "lucide-react";

export default function QuestionsPage() {
  const t = useTranslations("questions");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: ["questions", page],
    queryFn: () => fetchAllQuestions(page, 20),
  });

  const deleteMut = useMutation({
    mutationFn: deleteQuestion,
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["questions"] }); },
  });

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>;
  }

  const questions = data?.data ?? [];
  const meta = data?.meta;

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-semibold">{t("title")}</h1>

      <div className="overflow-x-auto rounded-lg border border-border">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("question")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("response")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("askedBy")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("date")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{tc("actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {questions.map((q) => (
              <tr key={q.id} className="hover:bg-muted/30">
                <td className="max-w-md truncate px-3 py-2">{q.question}</td>
                <td className="max-w-md truncate px-3 py-2 text-muted-foreground">
                  {q.response ?? "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {q.user_fullname ?? "—"}
                  <span className="ml-1.5 text-[10px]">{q.user_telnumber}</span>
                </td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{formatDateTime(q.created_at, locale)}</td>
                <td className="px-3 py-2">
                  <button onClick={() => deleteMut.mutate(q.id)} title={t("deleteQuestion")} className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
                    <Trash2 className="h-3.5 w-3.5" />
                  </button>
                </td>
              </tr>
            ))}
            {questions.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-muted-foreground">{tc("noData")}</td></tr>
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
