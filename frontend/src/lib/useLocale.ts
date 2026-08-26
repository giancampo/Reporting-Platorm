/**
 * The two i18n axes from action-plan.md §5, kept as separate hooks so a
 * component can never accidentally use one where the other belongs:
 * - `useUiLocale`: the signed-in user's UI language preference (`users.ui_language`).
 * - `useReportLocale`: the current project's report language (`projects.report_language`),
 *   which drives comment/PDF language regardless of who is viewing.
 */

import { createContext, useContext } from "react";
import type { SupportedLocale } from "../i18n";

export const UiLocaleContext = createContext<SupportedLocale>("en");
export const ReportLocaleContext = createContext<SupportedLocale>("en");

export function useUiLocale(): SupportedLocale {
  return useContext(UiLocaleContext);
}

export function useReportLocale(): SupportedLocale {
  return useContext(ReportLocaleContext);
}
