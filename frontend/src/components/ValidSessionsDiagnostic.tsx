import { t } from "../i18n";
import { formatNumber, formatPercent } from "../lib/format";
import { useUiLocale } from "../lib/useLocale";

/** action-plan.md §8: "three numbers side by side — GA sessions, valid
 * sessions, % discarded — plus a diagnostic table of the excluded segments.
 * The table is mandatory: the metric is only defensible with a client if
 * what was removed is visible." */
export interface ExcludedSegment {
  sourceMedium: string;
  browser: string;
  deviceCategory: string;
  os: string;
  screenResolutionBucket: string;
  sessions: number;
  reason: "hostname_filter" | "anomalous_segment";
}

export function ValidSessionsDiagnostic(props: {
  gaSessions: number;
  validSessions: number;
  excludedSegments: ExcludedSegment[];
}) {
  const locale = useUiLocale();
  const discardedPct = props.gaSessions === 0 ? 0 : (props.gaSessions - props.validSessions) / props.gaSessions;

  return (
    <section aria-label={t(locale, "validSessions.title")}>
      <h3>{t(locale, "validSessions.title")}</h3>
      <dl>
        <dt>{t(locale, "validSessions.gaSessions")}</dt>
        <dd>{formatNumber(props.gaSessions, locale)}</dd>
        <dt>{t(locale, "validSessions.validSessions")}</dt>
        <dd>{formatNumber(props.validSessions, locale)}</dd>
        <dt>{t(locale, "validSessions.discardedPct")}</dt>
        <dd>{formatPercent(discardedPct, locale)}</dd>
      </dl>
      {props.excludedSegments.length > 0 && (
        <table>
          <thead>
            <tr>
              <th>Source / medium</th>
              <th>Browser</th>
              <th>Device</th>
              <th>OS</th>
              <th>Screen</th>
              <th>Sessions</th>
              <th>Reason</th>
            </tr>
          </thead>
          <tbody>
            {props.excludedSegments.map((segment, i) => (
              <tr key={i}>
                <td>{segment.sourceMedium}</td>
                <td>{segment.browser}</td>
                <td>{segment.deviceCategory}</td>
                <td>{segment.os}</td>
                <td>{segment.screenResolutionBucket}</td>
                <td>{formatNumber(segment.sessions, locale)}</td>
                <td>{segment.reason}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
