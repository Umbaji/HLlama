import { redirect } from "next/navigation";
import { getLocale } from "next-intl/server";

export default async function LocaleIndexPage() {
  const locale = await getLocale();
  redirect(`/${locale}/overview`);
}
