/**
 * Server-side proxy to the FastAPI backend.
 *
 * The browser calls /api/backend/<path>; this handler forwards the request to
 * ${API_URL}/<path> and injects the X-API-Key header from the server-only
 * API_KEY env var. The key never reaches the client bundle (unlike a
 * NEXT_PUBLIC_ variable, which Next.js inlines into public JS).
 *
 * Env (server-side only):
 *   API_URL — backend base URL, default http://localhost:8000/api/v1
 *             (use http://api:8000/api/v1 inside docker compose)
 *   API_KEY — optional key sent as X-API-Key on every proxied request.
 *             If the backend's API_KEYS holds several keys, set the first one.
 */
import { NextRequest, NextResponse } from "next/server";

const API_URL = process.env.API_URL ?? "http://localhost:8000/api/v1";
const API_KEY = (process.env.API_KEY ?? "").split(",")[0].trim();

// Hop-by-hop / connection headers that must not be forwarded either way.
const STRIP_HEADERS = new Set([
  "host",
  "connection",
  "content-length",
  "transfer-encoding",
  "accept-encoding",
]);

async function proxy(
  req: NextRequest,
  { params }: { params: Promise<{ path: string[] }> },
): Promise<NextResponse> {
  const { path } = await params;
  const target = `${API_URL}/${path.join("/")}${req.nextUrl.search}`;

  const headers = new Headers();
  req.headers.forEach((value, key) => {
    if (!STRIP_HEADERS.has(key.toLowerCase())) headers.set(key, value);
  });
  if (API_KEY) headers.set("X-API-Key", API_KEY);

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers,
      body: req.method === "GET" || req.method === "HEAD" ? undefined : req.body,
      // Required by Node fetch when streaming a request body.
      // @ts-expect-error -- duplex is not in the TS lib types yet
      duplex: "half",
      cache: "no-store",
    });
  } catch {
    return NextResponse.json(
      { detail: `Backend unreachable at ${API_URL}` },
      { status: 502 },
    );
  }

  const responseHeaders = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!STRIP_HEADERS.has(key.toLowerCase())) responseHeaders.set(key, value);
  });

  return new NextResponse(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}

export {
  proxy as GET,
  proxy as POST,
  proxy as PUT,
  proxy as PATCH,
  proxy as DELETE,
};
