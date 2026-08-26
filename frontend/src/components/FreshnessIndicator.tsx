import { isStale } from "../lib/reportData";
import { t } from "../i18n";
import { formatDate } from "../lib/format";
import { useUiLocale } from "../lib/useLocale";

/** action-plan.md §13: "every page shows the date of the last successful
 * update for that project. It is the first place the analyst looks when a
 * number seems odd." */
export function FreshnessIndicator({ generatedAt }: { generatedAt: string }) {
  const locale = useUiLocale();
  const stale = isStale(generatedAt);

  return (
    <div role="status" data-stale={stale}>
      <span>{t(locale, "freshness.lastUpdated", { date: formatDate(generatedAt, locale, { dateStyle: "medium", timeStyle: "short" }) })}</span>
      {stale && <strong>{t(locale, "freshness.stale")}</strong>}
    </div>
  );
}
