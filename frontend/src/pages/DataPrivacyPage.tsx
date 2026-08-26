import { useEffect, useState } from "react";
import { t, resolveLocalizedText } from "../i18n";
import { supabase } from "../lib/supabaseClient";
import { useUiLocale } from "../lib/useLocale";
import type { LocalizedText } from "../lib/types";

/** action-plan.md §16: "a Data & Privacy page in the application, reachable
 * by every role." Text is loaded from the `legal_texts` config table
 * (supabase/migrations/0004_legal_texts.sql), never hardcoded here, so
 * updating it requires no deploy. */
export function DataPrivacyPage() {
  const locale = useUiLocale();
  const [disclaimer, setDisclaimer] = useState<LocalizedText | null>(null);

  useEffect(() => {
    supabase
      .from("legal_texts")
      .select("content")
      .eq("key", "data_residency_disclaimer")
      .single()
      .then(({ data }) => {
        if (data) setDisclaimer(data.content as LocalizedText);
      });
  }, []);

  return (
    <section>
      <h1>{t(locale, "nav.dataPrivacy")}</h1>
      {disclaimer ? (
        <div style={{ whiteSpace: "pre-wrap" }}>{resolveLocalizedText(disclaimer, locale)}</div>
      ) : (
        <p>Loading…</p>
      )}
    </section>
  );
}
