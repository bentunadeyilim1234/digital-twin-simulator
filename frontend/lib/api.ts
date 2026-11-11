// Thin HTTP client for the FastAPI engine. Requests go to same-origin /api/* and are
// proxied by Next.js rewrites; no data ever leaves for third-party hosts.

const WS_KEY = "ssrdt-workspace";

export function workspaceId(): string {
  if (typeof window === "undefined") return "default";
  try {
    let id = window.localStorage.getItem(WS_KEY);
    if (!id || !/^[A-Za-z0-9_-]{1,64}$/.test(id)) {
      id = "ws-" + Math.random().toString(36).slice(2, 12) + Date.now().toString(36).slice(-4);
      window.localStorage.setItem(WS_KEY, id);
    }
    return id;
  } catch {
    return "default";
  }
}

export class ApiError extends Error {
  status: number;
  errors?: string[];
  constructor(message: string, status: number, errors?: string[]) {
    super(message);
    this.status = status;
    this.errors = errors;
  }
}

async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "X-Workspace-Id": workspaceId() };
  let payload: BodyInit | undefined;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const res = await fetch(`/api${path}`, { method, headers, body: payload, cache: "no-store", ...init });
  if (!res.ok) {
    let detail = res.statusText;
    let errors: string[] | undefined;
    try {
      const j = await res.json();
      detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      errors = j.errors;
    } catch {
      /* non-JSON error */
    }
    throw new ApiError(detail || `HTTP ${res.status}`, res.status, errors);
  }
  const ct = res.headers.get("content-type") || "";
  if (ct.includes("application/json")) return (await res.json()) as T;
  return (await res.text()) as unknown as T;
}

export const api = {
  get: <T>(p: string) => request<T>("GET", p),
  post: <T>(p: string, b?: unknown) => request<T>("POST", p, b ?? {}),
  put: <T>(p: string, b: unknown) => request<T>("PUT", p, b),
  patch: <T>(p: string, b: unknown) => request<T>("PATCH", p, b),
  del: <T>(p: string) => request<T>("DELETE", p),
  form: <T>(p: string, fd: FormData) => request<T>("POST", p, fd),
};

/** Fetch a resource and trigger a browser download (CSV/MD/JSON exports). */
export async function download(path: string, filename: string, body?: unknown, method: "GET" | "POST" = "GET") {
  const headers: Record<string, string> = { "X-Workspace-Id": workspaceId() };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const res = await fetch(`/api${path}`, { method, headers, body: body !== undefined ? JSON.stringify(body) : undefined });
  if (!res.ok) throw new ApiError(`download failed (${res.status})`, res.status);
  const blob = await res.blob();
  saveBlob(blob, filename);
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function saveJson(data: unknown, filename: string) {
  saveBlob(new Blob([JSON.stringify(data, null, 2)], { type: "application/json" }), filename);
}
