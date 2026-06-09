import { createI18n } from "vue-i18n";
import en from "./locales/en";
import fr from "./locales/fr";

export const SUPPORTED_LOCALES = ["en", "fr"] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];

export const LOCALE_LABELS: Record<Locale, string> = {
  en: "English",
  fr: "Français",
};

const STORAGE_KEY = "syncbox.locale";

function isLocale(value: string | null): value is Locale {
  return value !== null && (SUPPORTED_LOCALES as readonly string[]).includes(value);
}

// Saved preference wins; otherwise follow the OS language (French UI for any
// fr-* system), falling back to English.
function detectLocale(): Locale {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (isLocale(saved)) return saved;
  } catch {
    /* localStorage unavailable — fall through to navigator */
  }
  const nav = typeof navigator !== "undefined" ? navigator.language.toLowerCase() : "en";
  return nav.startsWith("fr") ? "fr" : "en";
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectLocale(),
  fallbackLocale: "en",
  messages: { en, fr },
});

// Standalone translator usable outside component setup (Pinia stores, composables).
export const t = i18n.global.t;

export function getLocale(): Locale {
  return i18n.global.locale.value as Locale;
}

// Switch the active language and persist the choice for the next launch.
export function setLocale(locale: Locale): void {
  i18n.global.locale.value = locale;
  try {
    localStorage.setItem(STORAGE_KEY, locale);
  } catch {
    /* persistence is best-effort */
  }
  if (typeof document !== "undefined") {
    document.documentElement.setAttribute("lang", locale);
  }
}

// Reflect the initial locale on <html lang> for accessibility.
if (typeof document !== "undefined") {
  document.documentElement.setAttribute("lang", getLocale());
}
