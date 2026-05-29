// English-only at v2.0. Adding a locale = new file `./locales/<code>.ts` and a
// selection mechanism in the consumer apps. v2.2 adds: ar, ur, es.

import en from "./locales/en";

export type Locale = "en";

export const locales = { en } as const;

export function t(locale: Locale, key: keyof typeof en): string {
  return locales[locale][key] ?? en[key] ?? String(key);
}
