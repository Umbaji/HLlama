"use client";

import { useTranslations } from "next-intl";
import type { PaginationMeta } from "@/lib/types/api";

interface PaginationProps {
  meta: PaginationMeta | undefined;
  page: number;
  onPageChange: (page: number) => void;
}

export function Pagination({ meta, page, onPageChange }: PaginationProps) {
  const tc = useTranslations("common");
  if (!meta || meta.total_pages <= 1) return null;

  return (
    <div className="flex items-center justify-between text-xs text-muted-foreground">
      <span>
        {tc("page")} {meta.current_page} {tc("of")} {meta.total_pages}
      </span>
      <div className="flex gap-2">
        <button
          disabled={page <= 1}
          onClick={() => onPageChange(page - 1)}
          className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40"
        >
          {tc("previous")}
        </button>
        <button
          disabled={!meta.has_more}
          onClick={() => onPageChange(page + 1)}
          className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40"
        >
          {tc("next")}
        </button>
      </div>
    </div>
  );
}
