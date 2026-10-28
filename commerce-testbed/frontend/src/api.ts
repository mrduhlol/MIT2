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

// Monetary API fields retain their legacy *_cents names; values are INR paise.
export function formatPrice(paise: number): string {
  return (paise / 100).toLocaleString("en-IN", {
    style: "currency",
    currency: "INR",
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

  // Reads can recover from a transient edge failure without repeating writes.
  const attempts = method.toUpperCase() === "GET" ? 3 : 1;
  for (let attempt = 0; attempt < attempts; attempt++) {
    try {
      const res = await fetch(`${API_BASE_URL}${path}`, {
        method,
        headers,
        body: body !== undefined ? JSON.stringify(body) : undefined,
      });
      if (res.status === 401 && auth) {
        if (getToken()) handle401();
        throw new ApiError(401, "Not authenticated");
      }
      if (res.status === 204) return undefined as T;

      let data: unknown;
      try {
        data = await res.json();
      } catch {
        throw new ApiError(
          res.ok ? 502 : res.status,
          "The service is temporarily unavailable. Please try again.",
        );
      }
      if (!res.ok) {
        throw new ApiError(
          res.status,
          data && typeof data === "object" && "detail" in data
            ? data.detail
            : "The service is temporarily unavailable. Please try again.",
        );
      }
      if (data === null) {
        throw new ApiError(502, "The service returned an incomplete response. Please try again.");
      }
      return data as T;
    } catch (error) {
      const failure = error instanceof ApiError
        ? error
        : new ApiError(0, "Unable to connect. Check your connection and try again.");
      const retryable = failure.status === 0 || failure.status === 408 || failure.status === 429 || failure.status >= 500;
      if (!retryable || attempt === attempts - 1) throw failure;
      await new Promise((resolve) => setTimeout(resolve, 500 * 2 ** attempt));
    }
  }
  throw new ApiError(503, "The service is temporarily unavailable. Please try again.");
}
