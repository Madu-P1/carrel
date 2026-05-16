import {
  API_BASE,
  ApiError,
  BackendOfflineError,
  LOCAL_TOKEN_HEADER,
  resolveLocalApiToken
} from "@/services/api/client";

/**
 * Upload a file via `XMLHttpRequest` so the caller can subscribe to
 * per-byte progress events. `fetch` cannot report upload progress; the
 * dropzone UX ("Uploading foo.pdf ... 45%") needs XHR.
 *
 * Carrel's ingestion is loopback-only, so retry-on-network is
 * pointless (TCP to localhost doesn't blip). Chunked-resumable upload
 * is also overkill on localhost. The real UX value of this helper is
 * the progress event for multi-MB PDFs, where even loopback IO takes
 * a noticeable second.
 *
 * Imported pattern: Next.js examples that combine `<input type=file>`
 * with `xhr.upload.onprogress` for a live progress bar. Carries the
 * `X-Carrel-Local-Token` header so the backend's `/api/*` gate stays
 * intact.
 */

export interface UploadProgress {
  loaded: number;
  total: number;
  fraction: number;
}

export interface UploadWithProgressOptions {
  /** Extra `FormData` fields to send alongside the file. */
  fields?: Record<string, string>;
  /** Form field name for the file part. Defaults to `"file"`. */
  fileFieldName?: string;
  /** Called on every `upload.onprogress` event. `fraction` is 0..1. */
  onProgress?: (progress: UploadProgress) => void;
  /** Abort the in-flight request. */
  signal?: AbortSignal;
}

export interface UploadWithProgressResponse<T> {
  status: number;
  body: T;
}

export async function uploadWithProgress<T = unknown>(
  path: string,
  file: File,
  opts: UploadWithProgressOptions = {}
): Promise<UploadWithProgressResponse<T>> {
  const token = await resolveLocalApiToken();

  return new Promise<UploadWithProgressResponse<T>>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}${path}`, true);
    if (token) {
      xhr.setRequestHeader(LOCAL_TOKEN_HEADER, token);
    }

    xhr.upload.addEventListener("progress", (event) => {
      if (!opts.onProgress) return;
      const total = event.lengthComputable ? event.total : file.size;
      const loaded = event.loaded;
      opts.onProgress({
        loaded,
        total,
        fraction: total > 0 ? loaded / total : 0
      });
    });

    const onAbort = () => xhr.abort();
    if (opts.signal) {
      if (opts.signal.aborted) {
        reject(new DOMException("Aborted", "AbortError"));
        return;
      }
      opts.signal.addEventListener("abort", onAbort, { once: true });
    }

    xhr.addEventListener("error", () => {
      reject(new BackendOfflineError(new Error("network error")));
    });

    xhr.addEventListener("abort", () => {
      reject(new DOMException("Aborted", "AbortError"));
    });

    xhr.addEventListener("load", () => {
      if (opts.signal) opts.signal.removeEventListener("abort", onAbort);
      let parsed: unknown;
      try {
        parsed = xhr.responseText ? JSON.parse(xhr.responseText) : undefined;
      } catch {
        parsed = xhr.responseText;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve({ status: xhr.status, body: parsed as T });
      } else {
        reject(new ApiError(xhr.status, xhr.statusText, parsed));
      }
    });

    const form = new FormData();
    form.append(opts.fileFieldName ?? "file", file, file.name);
    for (const [key, value] of Object.entries(opts.fields ?? {})) {
      form.append(key, value);
    }
    xhr.send(form);
  });
}
