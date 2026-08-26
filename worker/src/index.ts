/**
 * Cloudflare Worker: validates the Supabase JWT, re-checks project access
 * against Supabase (reusing the RLS policies in supabase/migrations/0002_rls_policies.sql
 * as the single source of truth for "who can see this project" rather than
 * duplicating role logic here), then proxies the R2 GET.
 *
 * action-plan.md §10: "There must exist no path where the frontend requests
 * an R2 file without going through the Worker." This file is that path.
 */

import { jwtVerify } from "jose";

export interface Env {
  REPORTING_DATA: R2Bucket;
  SUPABASE_URL: string;
  SUPABASE_JWT_SECRET: string;
  SUPABASE_ANON_KEY: string;
}

// Matches the R2 key layout from etl/src/reporting_etl/storage/r2_writer.py —
// changing one without the other breaks every existing object.
const KEY_PATTERN =
  /^\/r2\/(?<projectSlug>[a-z0-9-]+)\/(?<source>[a-z0-9_]+)\/(?<reportKey>[a-z0-9_]+)\/(?<granularity>daily|monthly)\/(?<period>\d{4}-\d{2})\.json\.gz$/;

async function verifySupabaseJwt(token: string, secret: string): Promise<{ sub: string } | null> {
  try {
    const key = new TextEncoder().encode(secret);
    const { payload } = await jwtVerify(token, key, { algorithms: ["HS256"] });
    if (typeof payload.sub !== "string") return null;
    return { sub: payload.sub };
  } catch {
    return null; // expired, malformed, or signature mismatch — all treated as unauthenticated
  }
}

/** Re-validates project access via PostgREST, under the caller's own JWT so
 * RLS (project_users membership) decides — this Worker never has its own
 * elevated view of who can see what. */
async function callerCanAccessProject(
  env: Env,
  token: string,
  projectSlug: string
): Promise<boolean> {
  const url = `${env.SUPABASE_URL}/rest/v1/projects?slug=eq.${encodeURIComponent(projectSlug)}&select=id`;
  const response = await fetch(url, {
    headers: {
      apikey: env.SUPABASE_ANON_KEY,
      Authorization: `Bearer ${token}`,
    },
  });
  if (!response.ok) return false;
  const rows = (await response.json()) as unknown[];
  return rows.length > 0;
}

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);
    const match = KEY_PATTERN.exec(url.pathname);
    if (!match || !match.groups) {
      return new Response("Not found", { status: 404 });
    }

    const authHeader = request.headers.get("Authorization");
    if (!authHeader?.startsWith("Bearer ")) {
      return new Response("Missing bearer token", { status: 401 });
    }
    const token = authHeader.slice("Bearer ".length);

    const claims = await verifySupabaseJwt(token, env.SUPABASE_JWT_SECRET);
    if (!claims) {
      return new Response("Invalid or expired token", { status: 401 });
    }

    // Non-null: KEY_PATTERN requires every named group to participate in a match,
    // so if `match` succeeded, all five are guaranteed present.
    const groups = match.groups as Record<string, string>;
    const projectSlug = groups.projectSlug!;
    const source = groups.source!;
    const reportKey = groups.reportKey!;
    const granularity = groups.granularity!;
    const period = groups.period!;

    const allowed = await callerCanAccessProject(env, token, projectSlug);
    if (!allowed) {
      return new Response("Forbidden", { status: 403 });
    }

    const objectKey = `${projectSlug}/${source}/${reportKey}/${granularity}/${period}.json.gz`;
    const object = await env.REPORTING_DATA.get(objectKey);
    if (!object) {
      return new Response("Not found", { status: 404 });
    }

    const headers = new Headers();
    object.writeHttpMetadata(headers);
    headers.set("Content-Encoding", "gzip");
    headers.set("Cache-Control", "private, max-age=60"); // short TTL: files are rewritten nightly and mid-window

    return new Response(object.body, { headers });
  },
};
