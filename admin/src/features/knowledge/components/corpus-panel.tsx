"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslations } from "next-intl";
import { BookOpen, RefreshCw, ScanSearch, Check, X } from "lucide-react";
import {
  applyCorpusDocument,
  fetchCorpus,
  fetchCorpusDocument,
  scanCorpus,
} from "../services/knowledge-service";
import type { CorpusScan } from "../types/knowledge";

const STATUS_STYLE: Record<CorpusScan["status"], string> = {
  unchanged: "text-muted-foreground",
  changed: "text-amber-600",
  new: "text-primary",
  unreachable: "text-destructive",
  unreadable: "text-destructive",
  no_source: "text-muted-foreground",
};

export function CorpusPanel() {
  const t = useTranslations("knowledge.corpus");
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [diff, setDiff] = useState<CorpusScan | null>(null);

  const corpus = useQuery({ queryKey: ["corpus"], queryFn: fetchCorpus });
  const document = useQuery({
    queryKey: ["corpus-document", selected],
    queryFn: () => fetchCorpusDocument(selected as string),
    enabled: Boolean(selected),
  });
  const scan = useMutation({
    mutationFn: scanCorpus,
    onSuccess: (results) => {
      const changed = results.find((result) => result.status === "changed");
      setDiff(changed ?? results[0] ?? null);
      void queryClient.invalidateQueries({ queryKey: ["corpus"] });
    },
  });
  const apply = useMutation({
    mutationFn: ({ slug, content }: { slug: string; content: string }) => applyCorpusDocument(slug, content),
    onSuccess: () => {
      setDiff(null);
      void queryClient.invalidateQueries({ queryKey: ["corpus"] });
    },
  });

  return (
    <div className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{t("title")}</h2>
          <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
        </div>
        <button
          onClick={() => scan.mutate()}
          disabled={scan.isPending}
          className="flex items-center gap-2 border border-border px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted disabled:opacity-50"
        >
          <ScanSearch className="h-3.5 w-3.5" />
          {scan.isPending ? t("scanning") : t("scan")}
        </button>
      </header>

      {scan.isError ? <p className="text-xs text-destructive">{t("scanError")}</p> : null}

      {diff ? (
        <section className="border border-border">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <div className="flex items-center gap-2">
              <BookOpen className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="text-xs font-medium">{diff.title}</span>
              <span className={`text-xs ${STATUS_STYLE[diff.status]}`}>{t(`status.${diff.status}`)}</span>
            </div>
            <div className="flex items-center gap-2">
              {diff.status === "changed" ? (
                <button
                  onClick={() => apply.mutate({ slug: diff.slug, content: diff.new_content ?? "" })}
                  disabled={apply.isPending || !diff.new_content}
                  className="flex items-center gap-1.5 border border-border px-2.5 py-1 text-xs font-medium hover:bg-muted disabled:opacity-50"
                >
                  <Check className="h-3 w-3" />
                  {t("apply")}
                </button>
              ) : null}
              <button onClick={() => setDiff(null)} className="border border-border p-1 hover:bg-muted" aria-label={t("close")}>
                <X className="h-3 w-3" />
              </button>
            </div>
          </div>
          <pre className="max-h-72 overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-relaxed text-muted-foreground">
            {diff.diff || t("noDiff")}
          </pre>
        </section>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,22rem)_minmax(0,1fr)]">
        <section className="border border-border">
          <div className="border-b border-border px-3 py-2 text-xs font-medium">{t("documents")}</div>
          {corpus.isLoading ? <p className="px-3 py-6 text-xs text-muted-foreground">{t("loading")}</p> : null}
          {corpus.isError ? <p className="px-3 py-6 text-xs text-destructive">{t("loadError")}</p> : null}
          <ul className="max-h-[32rem] divide-y divide-border overflow-auto">
            {(corpus.data ?? []).map((item) => (
              <li key={item.slug}>
                <button
                  onClick={() => setSelected(item.slug)}
                  className={`w-full px-3 py-2 text-left transition-colors hover:bg-muted ${selected === item.slug ? "bg-primary/5" : ""}`}
                >
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-xs font-medium">{item.title}</span>
                    <span className="shrink-0 text-[11px] text-muted-foreground">{item.passages} p.</span>
                  </div>
                  <div className="mt-0.5 flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span className="uppercase tracking-wide">{item.language}</span>
                    <span className="truncate">{item.source}</span>
                    {item.published ? <span>{item.published}</span> : null}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="border border-border">
          <div className="flex items-center justify-between border-b border-border px-3 py-2">
            <span className="text-xs font-medium">{document.data?.title ?? t("reader")}</span>
            {document.data?.source_url ? (
              <a
                href={document.data.source_url}
                target="_blank"
                rel="noreferrer"
                className="flex items-center gap-1 text-[11px] text-primary hover:underline"
              >
                <RefreshCw className="h-3 w-3" />
                {t("source")}
              </a>
            ) : null}
          </div>
          {selected && document.isLoading ? <p className="px-3 py-6 text-xs text-muted-foreground">{t("loading")}</p> : null}
          {!selected ? <p className="px-3 py-6 text-xs text-muted-foreground">{t("select")}</p> : null}
          {document.data ? (
            <pre className="max-h-[32rem] overflow-auto whitespace-pre-wrap px-3 py-2 font-mono text-[11px] leading-relaxed text-foreground">
              {document.data.content}
            </pre>
          ) : null}
        </section>
      </div>
    </div>
  );
}
