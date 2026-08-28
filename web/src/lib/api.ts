import { auth } from "@/lib/auth";

const BASE = process.env.WHALETALE_API_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    /** Parsed `detail` when the API returned a structured error object. */
    readonly detail?: unknown,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

type Opts = {
  token?: string;
  method?: string;
  body?: unknown;
  cache?: RequestCache;
  revalidate?: number;
};

/** Call the operator API. Server-side only — the token stays out of the client. */
export async function api<T>(path: string, opts: Opts = {}): Promise<T> {
  const token = opts.token ?? (await auth())?.apiToken;
  if (!token) throw new ApiError(401, "not signed in");

  const res = await fetch(`${BASE}${path}`, {
    method: opts.method ?? "GET",
    headers: {
      Authorization: `Bearer ${token}`,
      ...(opts.body ? { "Content-Type": "application/json" } : {}),
    },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
    cache: opts.cache ?? (opts.revalidate === undefined ? "no-store" : undefined),
    next: opts.revalidate === undefined ? undefined : { revalidate: opts.revalidate },
  });

  if (!res.ok) {
    let message = res.statusText;
    let detail: unknown;
    try {
      const j = (await res.json()) as { detail?: unknown };
      detail = j.detail;
      if (typeof j.detail === "string") message = j.detail;
      else if (j.detail && typeof j.detail === "object" && "message" in j.detail) {
        message = String((j.detail as { message: unknown }).message);
      } else if (j.detail) message = JSON.stringify(j.detail);
    } catch {
      /* keep statusText */
    }
    throw new ApiError(res.status, message, detail);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
