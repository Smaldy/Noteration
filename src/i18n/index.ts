import i18n from "i18next";
import { initReactI18next } from "react-i18next";

import en from "@/locales/en/translation.json";
import es from "@/locales/es/translation.json";
import it from "@/locales/it/translation.json";

/** The languages Noteration ships. English is the default and the fallback. */
export const SUPPORTED_LANGUAGES = ["en", "it", "es"] as const;
export type Language = (typeof SUPPORTED_LANGUAGES)[number];

/** Native display names for the Settings language picker. */
export const LANGUAGE_NAMES: Record<Language, string> = {
  en: "English",
  it: "Italiano",
  es: "Español",
};

const LANG_STORAGE_KEY = "noteration.lang";

function isLanguage(value: string | null): value is Language {
  return value != null && (SUPPORTED_LANGUAGES as readonly string[]).includes(value);
}

/** Last-known language, cached so the first paint matches the saved choice
 *  before the backend Settings round-trip completes (avoids an English flash). */
export function cachedLanguage(): Language {
  try {
    const stored = localStorage.getItem(LANG_STORAGE_KEY);
    if (isLanguage(stored)) return stored;
  } catch {
    // localStorage unavailable (private mode / SSR) — fall back to English.
  }
  return "en";
}

/** Switch the active language: update i18next, the cache, and <html lang>. */
export function setLanguage(lang: string): void {
  const next = isLanguage(lang) ? lang : "en";
  void i18n.changeLanguage(next);
  try {
    localStorage.setItem(LANG_STORAGE_KEY, next);
  } catch {
    // best-effort cache; ignore write failures
  }
  document.documentElement.lang = next;
}

void i18n.use(initReactI18next).init({
  resources: {
    en: { translation: en },
    it: { translation: it },
    es: { translation: es },
  },
  lng: cachedLanguage(),
  fallbackLng: "en",
  interpolation: { escapeValue: false }, // React already escapes
});

document.documentElement.lang = i18n.language;

export default i18n;
