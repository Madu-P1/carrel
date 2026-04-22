export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  body?: unknown;
  status: number;
  statusText: string;

  constructor(status: number, statusText: string, body?: unknown) {
    super(`API ${status} ${statusText}`);
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

export type RequestInitEx = Omit<RequestInit, "body"> & { body?: BodyInit | object | null };

export async function api<T>(path: string, init: RequestInitEx = {}): Promise<T> {
  const { body, headers, ...rest } = init;
  const isObjectBody =
    body !== undefined && body !== null && !(body instanceof FormData) && typeof body === "object";

  const response = await fetch(`${API_BASE}${path}`, {
    ...rest,
    headers: {
      ...(isObjectBody ? { "content-type": "application/json" } : {}),
      ...headers
    },
    body: isObjectBody ? JSON.stringify(body) : (body as BodyInit | null | undefined)
  });

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    throw new ApiError(response.status, response.statusText, payload);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
