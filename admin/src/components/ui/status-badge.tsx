import { cn } from "@/lib/utils/cn";

export type StatusTone = "neutral" | "pending" | "success" | "danger";

const TONE_CLASSES: Record<StatusTone, string> = {
  neutral: "bg-muted text-muted-foreground",
  pending: "bg-amber-500/10 text-amber-700 dark:text-amber-400",
  success: "bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  danger: "bg-destructive/10 text-destructive",
};

export function StatusBadge({ tone, children }: { tone: StatusTone; children: React.ReactNode }) {
  return (
    <span className={cn("inline-flex rounded px-1.5 py-0.5 text-[10px] font-medium", TONE_CLASSES[tone])}>
      {children}
    </span>
  );
}
