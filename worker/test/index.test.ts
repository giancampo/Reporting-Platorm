import { SignJWT } from "jose";
import { beforeEach, describe, expect, it, vi } from "vitest";
import worker, { type Env } from "../src/index";

const JWT_SECRET = "test-secret-at-least-32-bytes-long!!";

async function makeToken(sub: string, opts: { expired?: boolean } = {}): Promise<string> {
  const key = new TextEncoder().encode(JWT_SECRET);
  const exp = opts.expired ? Math.floor(Date.now() / 1000) - 60 : Math.floor(Date.now() / 1000) + 3600;
  return new SignJWT({ sub })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime(exp)
    .sign(key);
}

function makeEnv(overrides: Partial<Env> = {}): Env {
  return {
    REPORTING_DATA: {
      get: vi.fn(),
    } as unknown as R2Bucket,
    SUPABASE_URL: "https://example.supabase.co",
    SUPABASE_JWT_SECRET: JWT_SECRET,
    SUPABASE_ANON_KEY: "anon-key",
    ...overrides,
  };
}

const VALID_PATH = "/r2/pilot/dummy/channels_overview/daily/2026-08.json.gz";

beforeEach(() => {
  vi.restoreAllMocks();
});

describe("Worker R2 proxy", () => {
  it("rejects requests with no Authorization header", async () => {
    const env = makeEnv();
    const res = await worker.fetch(new Request(`https://worker.example${VALID_PATH}`), env);
    expect(res.status).toBe(401);
  });

  it("rejects an expired token", async () => {
    const env = makeEnv();
    const token = await makeToken("user-1", { expired: true });
    const res = await worker.fetch(
      new Request(`https://worker.example${VALID_PATH}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      env
    );
    expect(res.status).toBe(401);
  });

  it("rejects a path that doesn't match the R2 key layout", async () => {
    const env = makeEnv();
    const token = await makeToken("user-1");
    const res = await worker.fetch(
      new Request("https://worker.example/r2/pilot/../etc/passwd", {
        headers: { Authorization: `Bearer ${token}` },
      }),
      env
    );
    expect(res.status).toBe(404);
  });

  it("returns 403 when the caller has no access to the project (RLS denies)", async () => {
    const env = makeEnv();
    const token = await makeToken("user-1");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))
    );
    const res = await worker.fetch(
      new Request(`https://worker.example${VALID_PATH}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      env
    );
    expect(res.status).toBe(403);
  });

  it("proxies the R2 object when the caller is authorized", async () => {
    const env = makeEnv();
    const token = await makeToken("user-1");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: "proj-1" }]), { status: 200 }))
    );
    const fakeObject = {
      body: new ReadableStream(),
      writeHttpMetadata: vi.fn(),
    };
    (env.REPORTING_DATA.get as ReturnType<typeof vi.fn>).mockResolvedValue(fakeObject);

    const res = await worker.fetch(
      new Request(`https://worker.example${VALID_PATH}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      env
    );

    expect(res.status).toBe(200);
    expect(env.REPORTING_DATA.get).toHaveBeenCalledWith(
      "pilot/dummy/channels_overview/daily/2026-08.json.gz"
    );
    expect(res.headers.get("Content-Encoding")).toBe("gzip");
  });

  it("returns 404 when authorized but the object doesn't exist yet", async () => {
    const env = makeEnv();
    const token = await makeToken("user-1");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(JSON.stringify([{ id: "proj-1" }]), { status: 200 }))
    );
    (env.REPORTING_DATA.get as ReturnType<typeof vi.fn>).mockResolvedValue(null);

    const res = await worker.fetch(
      new Request(`https://worker.example${VALID_PATH}`, {
        headers: { Authorization: `Bearer ${token}` },
      }),
      env
    );
    expect(res.status).toBe(404);
  });
});
