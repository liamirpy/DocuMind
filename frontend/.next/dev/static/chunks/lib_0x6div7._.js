(globalThis["TURBOPACK"] || (globalThis["TURBOPACK"] = [])).push([typeof document === "object" ? document.currentScript : undefined,
"[project]/lib/auth-api.ts [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "ApiError",
    ()=>ApiError,
    "apiFetch",
    ()=>apiFetch,
    "clearAccessToken",
    ()=>clearAccessToken,
    "loginAccount",
    ()=>loginAccount,
    "logoutAccount",
    ()=>logoutAccount,
    "refreshSession",
    ()=>refreshSession,
    "registerAccount",
    ()=>registerAccount
]);
// The browser always calls the public origin. Nginx owns /api and forwards it
// to the Express container, so no Docker hostname or public API URL is exposed.
const API_URL = "/api";
const AUTH_REQUEST_TIMEOUT_MS = 10_000;
async function authFetch(input, init = {}) {
    const controller = new AbortController();
    const timeout = window.setTimeout(()=>controller.abort(), AUTH_REQUEST_TIMEOUT_MS);
    try {
        return await fetch(input, {
            ...init,
            signal: controller.signal
        });
    } finally{
        window.clearTimeout(timeout);
    }
}
let accessToken = null;
let refreshInFlight = null;
class ApiError extends Error {
    status;
    constructor(message, status){
        super(message), this.status = status;
        this.name = "ApiError";
    }
}
async function readJson(response) {
    const contentType = response.headers.get("content-type") ?? "";
    if (!contentType.includes("application/json")) {
        return {};
    }
    return await response.json();
}
async function throwIfNotOk(response) {
    if (response.ok) return;
    const body = await readJson(response);
    const message = typeof body.error === "string" ? body.error : "Something went wrong. Please try again.";
    throw new ApiError(message, response.status);
}
function clearAccessToken() {
    accessToken = null;
}
async function registerAccount(input) {
    const response = await authFetch(`${API_URL}/auth/register`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        credentials: "include",
        body: JSON.stringify(input)
    });
    await throwIfNotOk(response);
    const body = await response.json();
    return body.user;
}
async function loginAccount(input) {
    const response = await authFetch(`${API_URL}/auth/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        credentials: "include",
        body: JSON.stringify(input)
    });
    await throwIfNotOk(response);
    const body = await response.json();
    accessToken = body.accessToken;
    return body;
}
async function refreshSession() {
    if (refreshInFlight) return refreshInFlight;
    refreshInFlight = (async ()=>{
        const response = await authFetch(`${API_URL}/auth/refresh-token`, {
            method: "POST",
            credentials: "include"
        });
        await throwIfNotOk(response);
        const body = await response.json();
        accessToken = body.accessToken;
        return body;
    })();
    try {
        return await refreshInFlight;
    } catch (error) {
        accessToken = null;
        throw error;
    } finally{
        refreshInFlight = null;
    }
}
async function logoutAccount() {
    try {
        await authFetch(`${API_URL}/auth/logout`, {
            method: "POST",
            credentials: "include"
        });
    } finally{
        accessToken = null;
    }
}
async function apiFetch(path, init = {}) {
    const send = (token)=>{
        const headers = new Headers(init.headers);
        if (token) {
            headers.set("Authorization", `Bearer ${token}`);
        }
        return fetch(`${API_URL}${path.startsWith("/") ? path : `/${path}`}`, {
            ...init,
            headers,
            credentials: "include"
        });
    };
    let response = await send(accessToken);
    if (response.status !== 401) {
        return response;
    }
    try {
        const refreshed = await refreshSession();
        response = await send(refreshed.accessToken);
    } catch  {
        accessToken = null;
    }
    return response;
}
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
"[project]/lib/auth-context.tsx [app-client] (ecmascript)", ((__turbopack_context__) => {
"use strict";

__turbopack_context__.s([
    "AuthProvider",
    ()=>AuthProvider,
    "useAuth",
    ()=>useAuth
]);
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/jsx-dev-runtime.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/node_modules/next/dist/compiled/react/index.js [app-client] (ecmascript)");
var __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$auth$2d$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__ = __turbopack_context__.i("[project]/lib/auth-api.ts [app-client] (ecmascript)");
;
var _s = __turbopack_context__.k.signature(), _s1 = __turbopack_context__.k.signature();
"use client";
;
;
const AuthContext = /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["createContext"])(null);
function AuthProvider({ children }) {
    _s();
    const [user, setUser] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])(null);
    const [status, setStatus] = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useState"])("loading");
    (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useEffect"])({
        "AuthProvider.useEffect": ()=>{
            let active = true;
            (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$auth$2d$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["refreshSession"])().then({
                "AuthProvider.useEffect": (response)=>{
                    if (!active) return;
                    setUser(response.user);
                    setStatus("authenticated");
                }
            }["AuthProvider.useEffect"]).catch({
                "AuthProvider.useEffect": (error)=>{
                    if (error instanceof Error && error.name === "AbortError") {
                        console.error("Session restore timed out. Check the /api proxy.");
                    }
                    if (!active) return;
                    setUser(null);
                    setStatus("unauthenticated");
                }
            }["AuthProvider.useEffect"]);
            return ({
                "AuthProvider.useEffect": ()=>{
                    active = false;
                }
            })["AuthProvider.useEffect"];
        }
    }["AuthProvider.useEffect"], []);
    const login = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useCallback"])({
        "AuthProvider.useCallback[login]": async (input)=>{
            const response = await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$auth$2d$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["loginAccount"])(input);
            setUser(response.user);
            setStatus("authenticated");
        }
    }["AuthProvider.useCallback[login]"], []);
    const register = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useCallback"])({
        "AuthProvider.useCallback[register]": async (input)=>{
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$auth$2d$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["registerAccount"])(input);
            await login({
                email: input.email,
                password: input.password
            });
        }
    }["AuthProvider.useCallback[register]"], [
        login
    ]);
    const logout = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useCallback"])({
        "AuthProvider.useCallback[logout]": async ()=>{
            await (0, __TURBOPACK__imported__module__$5b$project$5d2f$lib$2f$auth$2d$api$2e$ts__$5b$app$2d$client$5d$__$28$ecmascript$29$__["logoutAccount"])();
            setUser(null);
            setStatus("unauthenticated");
        }
    }["AuthProvider.useCallback[logout]"], []);
    const value = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useMemo"])({
        "AuthProvider.useMemo[value]": ()=>({
                user,
                status,
                login,
                register,
                logout
            })
    }["AuthProvider.useMemo[value]"], [
        user,
        status,
        login,
        register,
        logout
    ]);
    return /*#__PURE__*/ (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$jsx$2d$dev$2d$runtime$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["jsxDEV"])(AuthContext.Provider, {
        value: value,
        children: children
    }, void 0, false, {
        fileName: "[project]/lib/auth-context.tsx",
        lineNumber: 84,
        columnNumber: 10
    }, this);
}
_s(AuthProvider, "MUJE+70QuQm6qjjgPiwjHTvp6MI=");
_c = AuthProvider;
function useAuth() {
    _s1();
    const context = (0, __TURBOPACK__imported__module__$5b$project$5d2f$node_modules$2f$next$2f$dist$2f$compiled$2f$react$2f$index$2e$js__$5b$app$2d$client$5d$__$28$ecmascript$29$__["useContext"])(AuthContext);
    if (!context) {
        throw new Error("useAuth must be used inside AuthProvider");
    }
    return context;
}
_s1(useAuth, "b9L3QQ+jgeyIrH0NfHrJ8nn7VMU=");
var _c;
__turbopack_context__.k.register(_c, "AuthProvider");
if (typeof globalThis.$RefreshHelpers$ === 'object' && globalThis.$RefreshHelpers !== null) {
    __turbopack_context__.k.registerExports(__turbopack_context__.m, globalThis.$RefreshHelpers$);
}
}),
]);

//# sourceMappingURL=lib_0x6div7._.js.map