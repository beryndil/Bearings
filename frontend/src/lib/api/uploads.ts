/** Result of `POST /api/uploads` — the server persists the uploaded
 * bytes under a UUID name and hands back the absolute on-disk path,
 * which the drop handler injects into the prompt so Claude can read
 * it from disk. `filename` is the sanitized original name (basename
 * only, no path components) and is useful for a future attachment
 * chip; `size_bytes` and `mime_type` round out the display surface. */
export type Upload = {
  path: string;
  filename: string;
  size_bytes: number;
  mime_type: string;
};

/** Result of `POST /api/uploads/batch`. Wraps an ordered list of
 * `Upload` rows — order matches the request, which matters because
 * the composer injects `[File N]` tokens at the cursor in send order. */
export type UploadBatch = {
  uploads: Upload[];
};

/** Per-file progress payload reported during an upload. `loaded` is
 * bytes transferred so far; `total` is the total bytes the request
 * carries, or `null` when the browser can't compute a length (chunked
 * encoding, redirects). The drop pipeline shows a determinate bar when
 * `total` is known and falls back to a marquee otherwise. */
export type UploadProgress = {
  loaded: number;
  total: number | null;
};

/** Auth token storage key — duplicated from `core.ts` because the XHR
 * path doesn't share the `withAuth(init)` plumbing that wraps `fetch`.
 * Kept private to this module so a future move to `core.ts` only
 * touches the import on this side. */
const TOKEN_STORAGE_KEY = 'bearings:token';

function readAuthToken(): string | null {
  if (typeof localStorage === 'undefined') return null;
  try {
    return localStorage.getItem(TOKEN_STORAGE_KEY);
  } catch {
    return null;
  }
}

/** XHR-based POST that surfaces upload progress events. The reason we
 * use XHR rather than `fetch` here is `XMLHttpRequest.upload.onprogress`
 * — `fetch` exposes download progress but not upload progress in any
 * browser as of 2026. The Streams-based ReadableStream upload API
 * exists in Chromium but Firefox doesn't ship it; XHR is the only
 * cross-browser option for an honest progress bar.
 *
 * The function resolves with the parsed JSON on a 2xx; rejects with an
 * `Error` carrying the response body on any non-2xx (matching
 * `jsonFetch`'s shape so callers don't have to re-handle errors). */
function xhrPostJson<T>(
  url: string,
  body: FormData,
  onProgress?: (p: UploadProgress) => void
): Promise<T> {
  return new Promise<T>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    const token = readAuthToken();
    if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    if (onProgress) {
      xhr.upload.onprogress = (e: ProgressEvent) => {
        // `lengthComputable` flips false on chunked encodings or when
        // the browser can't size the body up front. Pass `null` so the
        // UI can render an indeterminate bar instead of a fake 0%.
        onProgress({
          loaded: e.loaded,
          total: e.lengthComputable ? e.total : null
        });
      };
    }
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText) as T);
        } catch (err) {
          reject(new Error(`POST ${url} → 200 but body was not JSON: ${String(err)}`));
        }
      } else {
        reject(new Error(`POST ${url} → ${xhr.status}: ${xhr.responseText}`));
      }
    };
    xhr.onerror = () => {
      reject(new Error(`POST ${url} → network error`));
    };
    xhr.onabort = () => {
      reject(new Error(`POST ${url} → aborted`));
    };
    xhr.send(body);
  });
}

/** Upload one File to `/api/uploads` and return the server-side path.
 *
 * The endpoint exists because Chrome on Wayland strips the URI
 * metadata from file drops even though `DataTransfer.files` still
 * carries the bytes. We read those bytes, POST them here, and inject
 * the resulting absolute path into the prompt — same shape as a
 * zenity/kdialog pick, just with an extra round-trip.
 *
 * Errors propagate as thrown `Error` instances (413 for over-size,
 * 415 for a blocked extension). The caller surfaces them via the
 * `dropDiagnostic` banner so the user sees the exact reason rather
 * than a silent failure.
 *
 * `onProgress` is optional — the drop pipeline passes a callback that
 * tees into a Svelte store so a multi-MB upload paints a real bar
 * instead of an opaque spinner. */
export function uploadFile(
  file: File,
  onProgress?: (p: UploadProgress) => void
): Promise<Upload> {
  const form = new FormData();
  // Field name must match the FastAPI handler's `file: UploadFile`
  // parameter. `file.name` is the browser-reported filename; the
  // server treats it as untrusted input and only extracts the suffix.
  form.append('file', file, file.name);
  return xhrPostJson<Upload>('/api/uploads', form, onProgress);
}

/** Upload multiple files in one round-trip via `/api/uploads/batch`.
 *
 * Collapses what used to be N serial single-file POSTs into a single
 * multipart request. Order is preserved end-to-end: the request keeps
 * the `files` parts in the order provided, and the route returns the
 * `uploads` array in the same order — which the composer relies on
 * for `[File N]` token injection. Failures are fail-fast: the first
 * file the server rejects (size cap, blocked extension, MIME
 * allowlist) aborts the batch with a 4xx and the caller surfaces the
 * banner; earlier files in the batch may have already committed to
 * disk (matching the single-file route's "commit then 413" semantics).
 *
 * `onProgress` reports CUMULATIVE bytes across the whole batch — not
 * per-file. That's what XHR's upload progress gives us natively
 * (one HTTP request = one progress stream), and it's the right unit
 * for the UI: the user dropped one batch, they want to see one bar. */
export function uploadFiles(
  files: File[],
  onProgress?: (p: UploadProgress) => void
): Promise<UploadBatch> {
  const form = new FormData();
  for (const file of files) {
    // Field name MUST match the FastAPI handler's
    // `files: list[UploadFile]` parameter. Multipart allows repeated
    // field names; the server reads them in order.
    form.append('files', file, file.name);
  }
  return xhrPostJson<UploadBatch>('/api/uploads/batch', form, onProgress);
}
