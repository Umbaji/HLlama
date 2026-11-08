"use client";

import { usePathname } from "@/i18n/navigation";
import { Link } from "@/i18n/navigation";
import { useTranslations } from "next-intl";
import {
  LayoutDashboard,
  Users,
  MessageSquare,
  ScrollText,
  Settings,
  ThumbsUp,
  LogOut,
  BookOpenText,
} from "lucide-react";
import { cn } from "@/lib/utils/cn";
import { useAuth } from "@/lib/hooks/use-auth";

interface NavItem {
  href: string;
  labelKey: string;
  icon: React.ComponentType<{ className?: string }>;
}

const NAV_ITEMS: NavItem[] = [
  { href: "/overview", labelKey: "dashboard.title", icon: LayoutDashboard },
  { href: "/users", labelKey: "users.title", icon: Users },
  { href: "/questions", labelKey: "questions.title", icon: MessageSquare },
  { href: "/knowledge", labelKey: "knowledge.title", icon: BookOpenText },
  { href: "/feedback", labelKey: "feedback.title", icon: ThumbsUp },
  { href: "/logs", labelKey: "logs.title", icon: ScrollText },
  { href: "/settings", labelKey: "settings.title", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const t = useTranslations();
  const { logout } = useAuth();

  return (
    <aside className="fixed left-0 top-0 z-40 flex h-screen w-60 flex-col border-r border-border bg-background">
      <div className="flex h-14 items-center border-b border-border px-5">
        <span className="text-sm font-semibold tracking-tight text-foreground">
          {t("common.appName")}
        </span>
      </div>

      <nav className="flex-1 space-y-0.5 px-3 py-4">
        {NAV_ITEMS.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "bg-primary/10 text-primary"
                  : "text-muted-foreground hover:bg-muted hover:text-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {t(item.labelKey)}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-border px-3 py-3">
        <button
          onClick={logout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
        >
          <LogOut className="h-4 w-4 shrink-0" />
          {t("common.logout")}
        </button>
      </div>
    </aside>
  );
}
