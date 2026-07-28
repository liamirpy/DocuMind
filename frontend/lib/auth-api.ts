import type {
  AuthResponse,
  LoginInput,
  RegisterInput,
  User,
} from "@/lib/types";

// The browser always calls the public origin. Nginx owns /api and forwards it
// to the Express container, so no Docker hostname or public API URL is exposed.
const API_URL = "/api";
const AUTH_REQUEST_TIMEOUT_MS = 10_000;

async function authFetch(
  input: RequestInfo | URL,
  init: RequestInit = {},
): Promise<Response> {
  const controller = new AbortController();
  const timeout = window.setTimeout(
    () => controller.abort(),
    AUTH_REQUEST_TIMEOUT_MS,
  );

  try {
    return await fetch(input, { ...init, signal: controller.signal });
  } finally {
    window.clearTimeout(timeout);
  }
}

let accessToken: string | null = null;
let refreshInFlight: Promise<AuthResponse> | null = null;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function readJson(response: Response): Promise<Record<string, unknown>> {
  const contentType = response.headers.get("content-type") ?? "";

  if (!contentType.includes("application/json")) {
    return {};
  }

  return (await response.json()) as Record<string, unknown>;
}

async function throwIfNotOk(response: Response): Promise<void> {
  if (response.ok) return;

  const body = await readJson(response);
  const message =
    typeof body.error === "string"
      ? body.error
      : "Something went wrong. Please try again.";

  throw new ApiError(message, response.status);
}

export function clearAccessToken(): void {
  accessToken = null;
}

export async function registerAccount(input: RegisterInput): Promise<User> {
  const response = await authFetch(`${API_URL}/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
  });

  await throwIfNotOk(response);
  const body = (await response.json()) as { user: User };
  return body.user;
}

export async function loginAccount(input: LoginInput): Promise<AuthResponse> {
  const response = await authFetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(input),
  });

  await throwIfNotOk(response);
  const body = (await response.json()) as AuthResponse;
  accessToken = body.accessToken;
  return body;
}

export async function refreshSession(): Promise<AuthResponse> {
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const response = await authFetch(`${API_URL}/auth/refresh-token`, {
      method: "POST",
      credentials: "include",
    });

    await throwIfNotOk(response);
    const body = (await response.json()) as AuthResponse;
    accessToken = body.accessToken;
    return body;
  })();

  try {
    return await refreshInFlight;
  } catch (error) {
    accessToken = null;
    throw error;
  } finally {
    refreshInFlight = null;
  }
}

export async function logoutAccount(): Promise<void> {
  try {
    await authFetch(`${API_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    accessToken = null;
  }
}

export async function apiFetch(
  path: string,
  init: RequestInit = {},
): Promise<Response> {
  const send = (token: string | null) => {
    const headers = new Headers(init.headers);

    if (token) {
      headers.set("Authorization", `Bearer ${token}`);
    }

    return fetch(`${API_URL}${path.startsWith("/") ? path : `/${path}`}`, {
      ...init,
      headers,
      credentials: "include",
    });
  };

  let response = await send(accessToken);

  if (response.status !== 401) {
    return response;
  }

  try {
    const refreshed = await refreshSession();
    response = await send(refreshed.accessToken);
  } catch {
    accessToken = null;
  }

  return response;
}
