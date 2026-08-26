/**
 * Fetches one R2-backed report document through the Worker (never directly
 * from R2 — action-plan.md §10). All filtering and dimension/metric
 * toggling happens client-side on the returned document via
 * `aggregation.ts`, per §6's "no queries, no latency, no marginal cost"
 * design.
 */

import { supabase } from "./supabaseClient";
import type { ReportDocument } from "./types";

const WORKER_URL = import.meta.env.VITE_WORKER_URL;

export class ReportFetchError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export async function fetchReportDocument(args: {
  projectSlug: string;
  source: string;
  reportKey: string;
  granularity: "daily" | "monthly";
  period: string; // 'YYYY-MM'
}): Promise<ReportDocument> {
  const { data: sessionData } = await supabase.auth.getSession();
  const accessToken = sessionData.session?.access_token;
  if (!accessToken) {
    throw new ReportFetchError(401, "Not authenticated.");
  }

  const path = `/r2/${args.projectSlug}/${args.source}/${args.reportKey}/${args.granularity}/${args.period}.json.gz`;
  const response = await fetch(`${WORKER_URL}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!response.ok) {
    throw new ReportFetchError(response.status, `Worker returned ${response.status} for ${path}`);
  }

  return (await response.json()) as ReportDocument;
}

/** Data-freshness indicator (action-plan.md §13): "every page shows the date
 * of the last successful update for that project." */
export function isStale(generatedAtIso: string, staleAfterHours = 30): boolean {
  const generatedAt = new Date(generatedAtIso).getTime();
  const ageHours = (Date.now() - generatedAt) / (1000 * 60 * 60);
  return ageHours > staleAfterHours;
}
