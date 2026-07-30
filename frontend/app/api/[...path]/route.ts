import type { NextRequest } from "next/server";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{ path: string[] }>;
};

const HOP_BY_HOP_HEADERS = [
  "connection",
  "content-encoding",
  "content-length",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

function getBackendBaseUrl(): string {
  const explicitTarget = process.env.API_PROXY_TARGET?.trim();

  if (explicitTarget) {
    return explicitTarget.replace(/\/$/, "");
  }

  const protocol = process.env.BACKEND_PROTOCOL?.trim() || "http";
  const host = process.env.BACKEND_HOST?.trim() || "127.0.0.1";
  const port = process.env.BACKEND_PORT?.trim() || "8080";

  return `${protocol}://${host}:${port}`;
}

async function proxyRequest(
  request: NextRequest,
  context: RouteContext,
): Promise<Response> {
  try {
    const { path } = await context.params;
    const encodedPath = path.map(encodeURIComponent).join("/");
    const upstreamUrl = new URL(
      `/api/${encodedPath}${request.nextUrl.search}`,
      `${getBackendBaseUrl()}/`,
    );

    const requestHeaders = new Headers(request.headers);
    requestHeaders.delete("host");
    requestHeaders.delete("content-length");
    requestHeaders.set("x-forwarded-host", request.nextUrl.host);
    requestHeaders.set(
      "x-forwarded-proto",
      request.nextUrl.protocol.replace(":", ""),
    );

    const init: RequestInit & { duplex?: "half" } = {
      method: request.method,
      headers: requestHeaders,
      redirect: "manual",
      cache: "no-store",
      signal: request.signal,
    };

    if (
      request.method !== "GET" &&
      request.method !== "HEAD" &&
      request.body
    ) {
      // Stream uploads to the backend instead of buffering entire files in RAM.
      init.body = request.body;
      init.duplex = "half";
    }

    const upstreamResponse = await fetch(upstreamUrl, init);
    const responseHeaders = new Headers(upstreamResponse.headers);

    for (const header of HOP_BY_HOP_HEADERS) {
      responseHeaders.delete(header);
    }

    // Preserve multiple Set-Cookie headers when the Node runtime exposes them.
    const setCookies = (
      upstreamResponse.headers as Headers & {
        getSetCookie?: () => string[];
      }
    ).getSetCookie?.();

    if (setCookies?.length) {
      responseHeaders.delete("set-cookie");
      for (const cookie of setCookies) {
        responseHeaders.append("set-cookie", cookie);
      }
    }

    return new Response(
      request.method === "HEAD" ? null : upstreamResponse.body,
      {
        status: upstreamResponse.status,
        statusText: upstreamResponse.statusText,
        headers: responseHeaders,
      },
    );
  } catch (error) {
    console.error("Backend proxy request failed", error);

    return Response.json(
      { error: "The backend service is unavailable." },
      { status: 502 },
    );
  }
}

export const GET = proxyRequest;
export const POST = proxyRequest;
export const PUT = proxyRequest;
export const PATCH = proxyRequest;
export const DELETE = proxyRequest;
export const OPTIONS = proxyRequest;
export const HEAD = proxyRequest;
