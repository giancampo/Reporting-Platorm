/**
 * Fetches one GCS-backed report document via the signing service (never
 * directly from GCS with a static credential, and never through anything
 * but this two-step path — action-plan.md §6, §10). All filtering and
 * dimension/metric toggling happens client-side on the returned document
 * via `aggregation.ts`, per §6's "no queries, no latency, no marginal
 * cost" design.
 *
 * Step 1: ask the signing service (Cloud Run, `signing-service/`) for a
 * short-lived V4 signed URL, authenticated with the Supabase access token —
 * the service re-checks project access via RLS before issuing one.
 * Step 2: fetch the object directly from that signed URL. No auth header
 * on this second request: the signed URL itself is the credential.
 */

import { supabase } from "./supabaseClient";
import type { ReportDocument } from "./types";

const SIGNING_SERVICE_URL = import.meta.env.VITE_SIGNING_SERVICE_URL;

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

  const path = `/objects/${args.projectSlug}/${args.source}/${args.reportKey}/${args.granularity}/${args.period}`;
  const signingResponse = await fetch(`${SIGNING_SERVICE_URL}${path}`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!signingResponse.ok) {
    throw new ReportFetchError(
      signingResponse.status,
      `Signing service returned ${signingResponse.status} for ${path}`
    );
  }

  const { url: signedUrl } = (await signingResponse.json()) as { url: string };
  const objectResponse = await fetch(signedUrl);

  if (!objectResponse.ok) {
    throw new ReportFetchError(objectResponse.status, `GCS returned ${objectResponse.status} for ${path}`);
  }

  return (await objectResponse.json()) as ReportDocument;
}

/** Data-freshness indicator (action-plan.md §13): "every page shows the date
 * of the last successful update for that project." */
export function isStale(generatedAtIso: string, staleAfterHours = 30): boolean {
  const generatedAt = new Date(generatedAtIso).getTime();
  const ageHours = (Date.now() - generatedAt) / (1000 * 60 * 60);
  return ageHours > staleAfterHours;
}
