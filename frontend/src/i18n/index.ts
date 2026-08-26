/**
 * Static UI string i18n (action-plan.md §5). `en` is the reference file and
 * must be complete; `it` may be partial, with automatic fallback to English
 * for anything missing — "never a blank label, never a machine translation."
 *
 * This is the STATIC-STRING mechanism only (buttons, menus, messages). The
 * separate mechanism for analyst-authored content (report titles, derived
 * metric labels, comments) is the per-locale JSONB `{en, it}` shape read
 * directly from Supabase — see `resolveLocalizedText` below, used against
 * `LocalizedText` from ./lib/types.
 */

import en from "./en.json";
import it from "./it.json";

export type SupportedLocale = "en" | "it";

const CATALOGS: Record<SupportedLocale, Record<string, string>> = { en, it };

const MISSING_KEYS_WARNED = new Set<string>();

/** Static-string lookup with EN fallback. `params` does simple
 * `{token}` interpolation — deliberately minimal, no ICU plural rules,
 * matching the current string set's needs. */
export function t(locale: SupportedLocale, key: string, params?: Record<string, string>): string {
  const catalog = CATALOGS[locale];
  let template = catalog[key];
  if (template === undefined) {
    template = CATALOGS.en[key];
    const warnKey = `${locale}:${key}`;
    if (template !== undefined && !MISSING_KEYS_WARNED.has(warnKey)) {
      MISSING_KEYS_WARNED.add(warnKey);
      // A missing translation is expected during Phase 3 rollout of `it`;
      // logging (not throwing) keeps it visible without breaking the UI.
      console.warn(`[i18n] Missing '${locale}' translation for key '${key}', falling back to 'en'.`);
    }
  }
  if (template === undefined) {
    throw new Error(`[i18n] Missing 'en' translation for key '${key}' — 'en' must be complete.`);
  }
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (_, token: string) => params[token] ?? `{${token}}`);
}

import type { LocalizedText } from "../lib/types";

/** Analyst-authored content lookup: `en` is mandatory, `it` optional with
 * fallback — never machine-translated (§5: "an automatically translated
 * text about to be sent to a client is exactly the kind of dependency this
 * plan rules out"). */
export function resolveLocalizedText(text: LocalizedText, locale: SupportedLocale): string {
  if (locale === "it" && text.it) return text.it;
  return text.en;
}
