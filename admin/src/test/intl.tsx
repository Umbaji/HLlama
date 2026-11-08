import { NextIntlClientProvider } from "next-intl";
import { renderToStaticMarkup } from "react-dom/server";
import type { ReactNode } from "react";
import getRequestConfig from "@/i18n/request";

/** The messages the application serves for a locale, read the way Next reads them. */
export async function messagesFor(locale: string) {
  const config = await getRequestConfig({ requestLocale: Promise.resolve(locale), locale: undefined as never });
  return { locale: config.locale as string, messages: config.messages as Record<string, unknown> };
}

/**
 * Renders a component with the application's real messages. A key that does
 * not exist is an error, not a silent fallback: `missing` lists them.
 */
export async function renderIntl(ui: ReactNode, locale = "en") {
  const { messages } = await messagesFor(locale);
  const missing: string[] = [];
  const html = renderToStaticMarkup(
    <NextIntlClientProvider
      locale={locale}
      messages={messages as never}
      timeZone="Africa/Lome"
      onError={(error) => missing.push(error.message)}
    >
      {ui}
    </NextIntlClientProvider>,
  );
  return { html, missing };
}
