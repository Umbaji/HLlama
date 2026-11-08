"use client";

import { useState } from "react";
import { useLocale, useTranslations } from "next-intl";
import { useQuery } from "@tanstack/react-query";
import { fetchFeedback } from "@/lib/api/feedback";
import { formatDateTime } from "@/lib/utils/format";
import { Pagination } from "@/components/ui/pagination";
import type { FeedbackAggregate } from "@/lib/types/api";

// The bot asks "usefulness" with three buttons: 3 Utile, 2 Moyen, 1 Pas utile.
const USEFULNESS_RATINGS = ["3", "2", "1"] as const;

export default function FeedbackPage() {
  const t = useTranslations("feedback");
  const locale = useLocale();
  const [page, setPage] = useState(1);
  const [questionKey, setQuestionKey] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["feedback", page, questionKey],
    queryFn: () => fetchFeedback(page, 20, questionKey || undefined),
  });

  // Aggregates are computed over every answer, not only this page: read them
  // unfiltered so the summary does not shrink when the list is filtered.
  const { data: summary } = useQuery({
    queryKey: ["feedback-summary"],
    queryFn: () => fetchFeedback(1, 1),
  });

  const aggregates = summary?.aggregates ?? [];
  const usefulness = aggregates.find((a) => a.question_key === "usefulness");
  const comments = aggregates.find((a) => a.question_key === "comment");
  const items = data?.items ?? [];

  const label = (key: string) => (t.has(`questions.${key}`) ? t(`questions.${key}`) : key);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-semibold">{t("title")}</h1>
        <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
      </div>

      <div className="grid gap-3 sm:grid-cols-3">
        <SummaryCard label={t("usefulnessAnswers")} value={usefulness?.rated_count ?? 0} />
        <SummaryCard
          label={t("usefulRate")}
          value={usefulRate(usefulness)}
          hint={t("usefulRateHint")}
        />
        <SummaryCard label={t("commentsCount")} value={comments?.count ?? 0} />
      </div>

      {usefulness && usefulness.rated_count > 0 && (
        <div className="rounded-lg border border-border p-4">
          <h2 className="mb-3 text-sm font-medium">{t("usefulnessBreakdown")}</h2>
          <div className="space-y-2">
            {USEFULNESS_RATINGS.map((rating) => {
              const count = usefulness.ratings[rating] ?? 0;
              const share = Math.round((count / usefulness.rated_count) * 100);
              return (
                <div key={rating} className="grid grid-cols-[6rem_1fr_5rem] items-center gap-3 text-xs">
                  <span>{t(`ratings.${rating}`)}</span>
                  <div className="h-2 overflow-hidden rounded bg-muted">
                    <div className="h-full rounded bg-primary" style={{ width: `${share}%` }} />
                  </div>
                  <span className="text-right tabular-nums text-muted-foreground">
                    {count} · {share} %
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="text-sm font-medium">{t("answers")}</h2>
          <select
            value={questionKey}
            onChange={(e) => {
              setQuestionKey(e.target.value);
              setPage(1);
            }}
            className="rounded border border-border bg-background px-2 py-1 text-xs"
            aria-label={t("question")}
          >
            <option value="">{t("allQuestions")}</option>
            {aggregates.map((a) => (
              <option key={a.question_key} value={a.question_key}>
                {label(a.question_key)}
              </option>
            ))}
          </select>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-20">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" />
          </div>
        ) : (
          <div className="overflow-x-auto rounded-lg border border-border">
            <table className="w-full text-left text-xs">
              <thead className="border-b border-border bg-muted/50">
                <tr>
                  <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("date")}</th>
                  <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("question")}</th>
                  <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("answer")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {items.map((item) => (
                  <tr key={item.id} className="align-top hover:bg-muted/30">
                    <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">
                      {formatDateTime(item.created_at, locale)}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{label(item.question_key)}</td>
                    <td className="max-w-xl px-3 py-2">
                      {item.answer ??
                        (item.rating !== null && item.question_key === "usefulness"
                          ? t(`ratings.${item.rating}`)
                          : item.rating ?? "—")}
                    </td>
                  </tr>
                ))}
                {items.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-3 py-6 text-center text-muted-foreground">
                      {t("empty")}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        <Pagination meta={data?.meta} page={page} onPageChange={setPage} />
      </div>
    </div>
  );
}

function usefulRate(aggregate: FeedbackAggregate | undefined): string {
  if (!aggregate || aggregate.rated_count === 0) return "—";
  return `${Math.round(((aggregate.ratings["3"] ?? 0) / aggregate.rated_count) * 100)} %`;
}

function SummaryCard({ label, value, hint }: { label: string; value: number | string; hint?: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="mt-1 text-2xl font-semibold tabular-nums">{value}</p>
      {hint && <p className="mt-1 text-[10px] text-muted-foreground">{hint}</p>}
    </div>
  );
}
