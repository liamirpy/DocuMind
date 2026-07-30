module.exports = [
"[externals]/next/dist/compiled/next-server/app-route-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-route-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-route-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/@opentelemetry/api [external] (next/dist/compiled/@opentelemetry/api, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/@opentelemetry/api", () => require("next/dist/compiled/@opentelemetry/api"));

module.exports = mod;
}),
"[externals]/next/dist/compiled/next-server/app-page-turbo.runtime.dev.js [external] (next/dist/compiled/next-server/app-page-turbo.runtime.dev.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js", () => require("next/dist/compiled/next-server/app-page-turbo.runtime.dev.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-unit-async-storage.external.js [external] (next/dist/server/app-render/work-unit-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-unit-async-storage.external.js", () => require("next/dist/server/app-render/work-unit-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/server/app-render/work-async-storage.external.js [external] (next/dist/server/app-render/work-async-storage.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/server/app-render/work-async-storage.external.js", () => require("next/dist/server/app-render/work-async-storage.external.js"));

module.exports = mod;
}),
"[externals]/next/dist/shared/lib/no-fallback-error.external.js [external] (next/dist/shared/lib/no-fallback-error.external.js, cjs)", ((__turbopack_context__, module, exports) => {

const mod = __turbopack_context__.x("next/dist/shared/lib/no-fallback-error.external.js", () => require("next/dist/shared/lib/no-fallback-error.external.js"));

module.exports = mod;
}),
"[project]/app/api/[...path]/route.ts [app-route] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "DELETE",
    ()=>DELETE,
    "GET",
    ()=>GET,
    "HEAD",
    ()=>HEAD,
    "OPTIONS",
    ()=>OPTIONS,
    "PATCH",
    ()=>PATCH,
    "POST",
    ()=>POST,
    "PUT",
    ()=>PUT,
    "dynamic",
    ()=>dynamic,
    "runtime",
    ()=>runtime
]);
const runtime = "nodejs";
const dynamic = "force-dynamic";
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
    "upgrade"
];
function getBackendBaseUrl() {
    const explicitTarget = process.env.API_PROXY_TARGET?.trim();
    if (explicitTarget) {
        return explicitTarget.replace(/\/$/, "");
    }
    const protocol = process.env.BACKEND_PROTOCOL?.trim() || "http";
    const host = process.env.BACKEND_HOST?.trim() || "127.0.0.1";
    const port = process.env.BACKEND_PORT?.trim() || "8080";
    return `${protocol}://${host}:${port}`;
}
async function proxyRequest(request, context) {
    try {
        const { path } = await context.params;
        const encodedPath = path.map(encodeURIComponent).join("/");
        const upstreamUrl = new URL(`/api/${encodedPath}${request.nextUrl.search}`, `${getBackendBaseUrl()}/`);
        const requestHeaders = new Headers(request.headers);
        requestHeaders.delete("host");
        requestHeaders.delete("content-length");
        requestHeaders.set("x-forwarded-host", request.nextUrl.host);
        requestHeaders.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
        const init = {
            method: request.method,
            headers: requestHeaders,
            redirect: "manual",
            cache: "no-store",
            signal: request.signal
        };
        if (request.method !== "GET" && request.method !== "HEAD" && request.body) {
            // Stream uploads to the backend instead of buffering entire files in RAM.
            init.body = request.body;
            init.duplex = "half";
        }
        const upstreamResponse = await fetch(upstreamUrl, init);
        const responseHeaders = new Headers(upstreamResponse.headers);
        for (const header of HOP_BY_HOP_HEADERS){
            responseHeaders.delete(header);
        }
        // Preserve multiple Set-Cookie headers when the Node runtime exposes them.
        const setCookies = upstreamResponse.headers.getSetCookie?.();
        if (setCookies?.length) {
            responseHeaders.delete("set-cookie");
            for (const cookie of setCookies){
                responseHeaders.append("set-cookie", cookie);
            }
        }
        return new Response(request.method === "HEAD" ? null : upstreamResponse.body, {
            status: upstreamResponse.status,
            statusText: upstreamResponse.statusText,
            headers: responseHeaders
        });
    } catch (error) {
        console.error("Backend proxy request failed", error);
        return Response.json({
            error: "The backend service is unavailable."
        }, {
            status: 502
        });
    }
}
const GET = proxyRequest;
const POST = proxyRequest;
const PUT = proxyRequest;
const PATCH = proxyRequest;
const DELETE = proxyRequest;
const OPTIONS = proxyRequest;
const HEAD = proxyRequest;
}),
];

//# sourceMappingURL=%5Broot-of-the-server%5D__0har2fo._.js.map