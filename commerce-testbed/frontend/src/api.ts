const TOKEN_KEY = "ct_token";
const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

export function setToken(token: string) {
  localStorage.setItem(TOKEN_KEY, token);
}

export function clearToken() {
  localStorage.removeItem(TOKEN_KEY);
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
    this.status = status;
    this.detail = detail;
  }

  /** Human-friendly message from FastAPI error shape. */
  get message(): string {
    if (typeof this.detail === "string") return this.detail;
    if (Array.isArray(this.detail)) {
      const parts = (this.detail as { msg?: string; loc?: unknown[] }[]).map(
        (d) =>
          d.msg
            ? [d.loc?.slice(-1)[0] ?? "", d.msg].filter(Boolean).join(": ")
            : JSON.stringify(d),
      );
      return parts.join(" • ");
    }
    if (this.detail && typeof this.detail === "object") {
      const obj = this.detail as Record<string, unknown>;
      if (typeof obj.detail === "string") return obj.detail;
    }
    return this.status === 401
      ? "Your session has expired. Please log in again."
      : "Something went wrong. Please try again.";
  }
}

export function formatPrice(cents: number): string {
  return (cents / 100).toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

interface ApiOptions {
  method?: string;
  body?: unknown;
  auth?: boolean;
}

/** On 401 with an attached token: clear it and bounce to /login. */
function handle401() {
  clearToken();
  if (!window.location.pathname.startsWith("/login")) {
    window.location.assign(
      `/login?next=${encodeURIComponent(
        window.location.pathname + window.location.search,
      )}`,
    );
  }
}

export async function api<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const { method = "GET", body, auth = true } = options;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (auth) {
    const token = getToken();
    if (token) headers["Authorization"] = `Bearer ${token}`;
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError(0, "Network error — is the API server running?");
  }

  if (res.status === 401 && auth) {
    if (getToken()) handle401();
    throw new ApiError(401, "Not authenticated");
  }
  if (res.status === 204) {
    return undefined as T;
  }
  let data: unknown = null;
  try {
    data = await res.json();
    if (
      data &&
      typeof data === "object" &&
      "detail" in (data as Record<string, unknown>) &&
      !res.ok
    ) {
      const wrapped = (data as Record<string, unknown>).detail;
      if (typeof wrapped === "string") {
        data = { detail: wrapped };
      }
    }
  } catch {
    // no body
  }
  if (!res.ok) {
    throw new ApiError(res.status, data ?? res.statusText);
  }
  return data as T;
}
