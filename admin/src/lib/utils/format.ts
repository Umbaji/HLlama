import { format, parseISO } from "date-fns";
import { fr, enUS } from "date-fns/locale";

const localeMap = { fr, en: enUS } as const;

export function formatDate(dateStr: string, locale: string = "fr"): string {
  const dateLocale = localeMap[locale as keyof typeof localeMap] ?? fr;
  return format(parseISO(dateStr), "dd MMM yyyy", { locale: dateLocale });
}

export function formatDateTime(dateStr: string, locale: string = "fr"): string {
  const dateLocale = localeMap[locale as keyof typeof localeMap] ?? fr;
  return format(parseISO(dateStr), "dd MMM yyyy HH:mm", { locale: dateLocale });
}

export function formatAmount(amount: number, currency: string = "XOF", locale: string = "fr"): string {
  const value = new Intl.NumberFormat(locale === "en" ? "en-US" : "fr-FR").format(amount);
  return currency === "XOF" ? `${value} F CFA` : `${value} ${currency}`;
}
