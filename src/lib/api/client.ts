// Real API client. Talks to the FastAPI backend; response shapes are the backend's own and are
// translated for the UI by the functions in src/lib/adapters.
import { CLERK_ENABLED } from "@/lib/auth-config";
import type { Role } from "@/lib/types";
import { useAuthStore, useTenantStore } from "@/stores";

// The bundled mock API is only used when this is explicitly switched on.
export const USE_MOCK = process.env.NEXT_PUBLIC_USE_MOCK === "true";
export const BACKEND_URL = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");

export const BACKEND_ROLE: Record<Role, string> = {
  admin: "admin",
  investigator: "siu_investigator",
  analyst: "analyst",
  viewer: "viewer",
};

export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
    public code = "ERROR",
    public details: Record<string, unknown> = {},
  ) {
    super(message);
  }
}

const tokens = new Map<string, { token: string; expires: number }>();

async function parseError(res: Response): Promise<ApiError> {
  let message = `Request failed (${res.status}).`;
  let code = "ERROR";
  let details = {};
  try {
    const body = await res.json();
    message = body?.error?.message ?? body?.detail ?? message;
    code = body?.error?.code ?? code;
    details = body?.error?.details ?? {};
  } catch {}
  return new ApiError(message, res.status, code, details);
}

async function devToken(tenant: string, platformAdmin: boolean): Promise<string> {
  const { user, role } = useAuthStore.getState();
  const subject = user?.id ?? "VWR-021";
  const key = `${tenant}|${subject}|${role}|${platformAdmin}`;
  const cached = tokens.get(key);
  if (cached && cached.expires > Date.now()) return cached.token;
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}/api/v1/auth/dev-token`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ tenant, user: subject, role: BACKEND_ROLE[role], platform_admin: platformAdmin }),
    });
  } catch {
    throw new ApiError(`The backend at ${BACKEND_URL} is not reachable. Start it with "uvicorn app.main:app" in the backend folder.`, 0, "BACKEND_UNREACHABLE");
  }
  if (!res.ok) throw await parseError(res);
  const body = await res.json();
  tokens.set(key, { token: body.access_token, expires: Date.now() + (body.expires_in_minutes - 5) * 60_000 });
  return body.access_token;
}

async function bearer(tenant: string): Promise<string> {
  if (CLERK_ENABLED) {
    // Production sign-in: the backend verifies the Clerk session token (CLERK_JWKS_URL).
    const clerk = (window as unknown as { Clerk?: { session?: { getToken: () => Promise<string | null> } } }).Clerk;
    const token = await clerk?.session?.getToken();
    if (!token) throw new ApiError("You are signed out. Sign in again.", 401, "UNAUTHORIZED");
    return token;
  }
  // Demo sign-in: the backend's development token endpoint stands in for an identity provider.
  // The demo Admin is also a platform administrator so tenant management screens work.
  return devToken(tenant, useAuthStore.getState().role === "admin");
}

export interface BackendInit {
  method?: "GET" | "POST";
  body?: unknown;
  tenant?: string;
  query?: Record<string, string | number | boolean | null | undefined>;
  blob?: boolean;
  auth?: boolean;
}

export async function backend<T>(path: string, init: BackendInit = {}): Promise<T> {
  const tenant = init.tenant ?? useTenantStore.getState().tenantId;
  const headers: Record<string, string> = {};
  if (init.auth !== false) headers.authorization = `Bearer ${await bearer(tenant)}`;
  if (CLERK_ENABLED && init.tenant) headers["x-tenant-id"] = tenant;
  if (init.body !== undefined) headers["content-type"] = "application/json";
  const qs = Object.entries(init.query ?? {})
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
    .join("&");
  const prefix = path.startsWith("/health") || path === "/metrics" ? "" : "/api/v1";
  let res: Response;
  try {
    res = await fetch(`${BACKEND_URL}${prefix}${path}${qs ? `?${qs}` : ""}`, {
      method: init.method ?? "GET",
      headers,
      body: init.body === undefined ? undefined : JSON.stringify(init.body),
    });
  } catch {
    throw new ApiError(`The backend at ${BACKEND_URL} is not reachable. Check that it is running.`, 0, "BACKEND_UNREACHABLE");
  }
  if (!res.ok) throw await parseError(res);
  return (init.blob ? res.blob() : res.json()) as Promise<T>;
}
