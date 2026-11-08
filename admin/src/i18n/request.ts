import { getRequestConfig } from "next-intl/server";
import { locales, defaultLocale, type Locale } from "./config";

import commonFr from "@/messages/fr/common.json";
import authFr from "@/messages/fr/auth.json";
import dashboardFr from "@/messages/fr/dashboard.json";
import usersFr from "@/messages/fr/users.json";
import questionsFr from "@/messages/fr/questions.json";
import logsFr from "@/messages/fr/logs.json";
import settingsFr from "@/messages/fr/settings.json";
import feedbackFr from "@/messages/fr/feedback.json";
import knowledgeFr from "@/messages/fr/knowledge.json";

import commonEn from "@/messages/en/common.json";
import authEn from "@/messages/en/auth.json";
import dashboardEn from "@/messages/en/dashboard.json";
import usersEn from "@/messages/en/users.json";
import questionsEn from "@/messages/en/questions.json";
import logsEn from "@/messages/en/logs.json";
import settingsEn from "@/messages/en/settings.json";
import feedbackEn from "@/messages/en/feedback.json";
import knowledgeEn from "@/messages/en/knowledge.json";

type MessageValue = string | Record<string, string | Record<string, string>>;
type Messages = Record<string, Record<string, MessageValue>>;

const messagesByLocale: Record<Locale, Messages> = {
  fr: {
    common: commonFr,
    auth: authFr,
    dashboard: dashboardFr,
    users: usersFr,
    questions: questionsFr,
    logs: logsFr,
    settings: settingsFr,
    feedback: feedbackFr,
    knowledge: knowledgeFr,
  },
  en: {
    common: commonEn,
    auth: authEn,
    dashboard: dashboardEn,
    users: usersEn,
    questions: questionsEn,
    logs: logsEn,
    settings: settingsEn,
    feedback: feedbackEn,
    knowledge: knowledgeEn,
  },
};

function mergeMessages(locale: Locale): Messages {
  return messagesByLocale[locale];
}

export default getRequestConfig(async ({ requestLocale }) => {
  const requested = await requestLocale;
  const locale: Locale = locales.includes(requested as Locale)
    ? (requested as Locale)
    : defaultLocale;

  return {
    locale,
    messages: mergeMessages(locale),
  };
});
