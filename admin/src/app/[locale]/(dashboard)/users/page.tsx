"use client";

import { useState } from "react";
import { useTranslations } from "next-intl";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { fetchUsers, fetchAdmins, activateUser, deactivateUser, deleteUser, promoteUser, demoteUser } from "@/lib/api/users";
import { formatDate } from "@/lib/utils/format";
import { useLocale } from "next-intl";
import { Shield, ShieldOff, UserX, UserCheck, Trash2 } from "lucide-react";

type Filter = "all" | "users" | "admins";

export default function UsersPage() {
  const t = useTranslations("users");
  const tc = useTranslations("common");
  const locale = useLocale();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);
  const [filter, setFilter] = useState<Filter>("all");

  const { data, isLoading } = useQuery({
    queryKey: ["users", filter, page],
    queryFn: () => {
      if (filter === "admins") return fetchAdmins(page, 15);
      return fetchUsers(page, 15);
    },
  });

  const mutationOpts = {
    onSuccess: () => { void queryClient.invalidateQueries({ queryKey: ["users"] }); },
  };

  const deactivateMut = useMutation({ mutationFn: deactivateUser, ...mutationOpts });
  const activateMut = useMutation({ mutationFn: activateUser, ...mutationOpts });
  const deleteMut = useMutation({ mutationFn: deleteUser, ...mutationOpts });
  const promoteMut = useMutation({ mutationFn: promoteUser, ...mutationOpts });
  const demoteMut = useMutation({ mutationFn: demoteUser, ...mutationOpts });

  const handleFilterChange = (f: Filter) => {
    setFilter(f);
    setPage(1);
  };

  if (isLoading) {
    return <div className="flex items-center justify-center py-20"><div className="h-5 w-5 animate-spin rounded-full border-2 border-primary border-t-transparent" /></div>;
  }

  let users = data?.data ?? [];
  const meta = data?.meta;

  if (filter === "users") {
    users = users.filter((u) => !u.is_admin);
  }

  const filters: { value: Filter; label: string }[] = [
    { value: "all", label: t("all") },
    { value: "users", label: t("usersOnly") },
    { value: "admins", label: t("adminsOnly") },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-base font-semibold">{t("title")}</h1>
        <div className="flex items-center gap-1 rounded-md border border-border bg-muted/40 p-0.5">
          {filters.map((f) => (
            <button
              key={f.value}
              onClick={() => handleFilterChange(f.value)}
              className={`rounded px-2.5 py-1 text-[11px] font-medium transition-colors ${
                filter === f.value
                  ? "bg-background text-foreground shadow-sm"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-md border border-border">
        <table className="w-full text-left text-xs">
          <thead className="border-b border-border bg-muted/50">
            <tr>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("fullname")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("phone")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("email")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("location")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("role")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{tc("status")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{t("createdAt")}</th>
              <th className="px-3 py-2.5 font-medium text-muted-foreground">{tc("actions")}</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {users.map((user) => (
              <tr key={user.id} className="hover:bg-muted/30">
                <td className="px-3 py-2 font-medium">{user.fullname ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{user.telnumber}</td>
                <td className="px-3 py-2 text-muted-foreground">{user.email}</td>
                <td className="px-3 py-2 text-muted-foreground">{user.location ?? "—"}</td>
                <td className="px-3 py-2">
                  {user.is_admin ? (
                    <span className="inline-flex items-center gap-1 rounded-full bg-indigo-50 px-2 py-0.5 text-[10px] font-semibold text-indigo-700">
                      <Shield className="h-2.5 w-2.5" />
                      {t("admin")}
                    </span>
                  ) : (
                    <span className="text-[10px] text-muted-foreground">{t("user")}</span>
                  )}
                </td>
                <td className="px-3 py-2">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-[10px] font-medium ${user.is_active ? "bg-emerald-50 text-emerald-700" : "bg-red-50 text-red-700"}`}>
                    {user.is_active ? tc("active") : tc("inactive")}
                  </span>
                </td>
                <td className="px-3 py-2 tabular-nums text-muted-foreground">{formatDate(user.created_at, locale)}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1">
                    {user.is_active ? (
                      <button onClick={() => deactivateMut.mutate(user.id)} title={t("deactivate")} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-amber-600">
                        <UserX className="h-3.5 w-3.5" />
                      </button>
                    ) : (
                      <button onClick={() => activateMut.mutate(user.id)} title={t("activate")} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-emerald-600">
                        <UserCheck className="h-3.5 w-3.5" />
                      </button>
                    )}
                    {!user.is_admin ? (
                      <button onClick={() => promoteMut.mutate(user.id)} title={t("promote")} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-blue-600">
                        <Shield className="h-3.5 w-3.5" />
                      </button>
                    ) : (
                      <button onClick={() => demoteMut.mutate(user.id)} title={t("demote")} className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-orange-600">
                        <ShieldOff className="h-3.5 w-3.5" />
                      </button>
                    )}
                    <button onClick={() => deleteMut.mutate(user.id)} title={t("deleteUser")} className="rounded p-1 text-muted-foreground hover:bg-destructive/10 hover:text-destructive">
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {meta && meta.total_pages > 1 && (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{tc("page")} {meta.current_page} {tc("of")} {meta.total_pages} ({meta.total_count} {tc("total")})</span>
          <div className="flex gap-2">
            <button disabled={page <= 1} onClick={() => setPage(page - 1)} className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40">{tc("previous")}</button>
            <button disabled={!meta.has_more} onClick={() => setPage(page + 1)} className="rounded border border-border px-2.5 py-1 hover:bg-muted disabled:opacity-40">{tc("next")}</button>
          </div>
        </div>
      )}
    </div>
  );
}
