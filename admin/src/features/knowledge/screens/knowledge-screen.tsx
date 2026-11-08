"use client";

import { useTranslations } from "next-intl";
import { CorpusPanel } from "../components/corpus-panel";

export function KnowledgeScreen() {
  const t = useTranslations("knowledge");

  return (
    <div className="space-y-4">
      <header>
        <h1 className="text-lg font-semibold">{t("title")}</h1>
        <p className="text-xs text-muted-foreground">{t("subtitle")}</p>
      </header>
      <CorpusPanel />
    </div>
  );
}
