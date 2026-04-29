/**
 * Tiny typed fetch wrapper — the one place the rest of the frontend
 * goes through to call the backend. Centralising it keeps:
 *
 * - error handling consistent (a non-2xx response throws an
 *   :class:`ApiError` whose ``status`` + ``body`` carry the FastAPI
 *   ``detail`` payload through to the caller);
 * - typed-response decoding consistent (the caller hands in the
 *   expected shape; the wrapper does the JSON parse and the cast);
 * - ``AbortSignal`` plumbing consistent so a store that re-fetches
 *   while a previous request is in flight can cancel cleanly.
 *
 * Per arch §1.2 each backend route group gets its own thin client
 * module (``api/sessions.ts``, ``api/tags.ts``, etc.) that calls into
 * this wrapper. The wrapper is intentionally narrow — no retry, no
 * caching, no auth munging — those concerns are added by the modules
 * that need them rather than baked in here.
 */
const HTTP_OK_MIN = 200;
const HTTP_OK_MAX = 300;

/**
 * Thrown when the server returns a non-2xx response. The caller can
 * branch on ``error.status`` for 404 / 409 / etc. handling without
 * re-parsing the response body.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly body: unknown;

  constructor(status: number, body: unknown, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export interface RequestOptions {
  signal?: AbortSignal;
  /** Repeated query-param entries; produces ``?k=v1&k=v2`` for the OR-filter shape. */
  query?: Iterable<readonly [string, string]>;
}

/**
 * Issue a GET against ``path``, decode the JSON body, and return it
 * cast to ``T``. The cast is unchecked at runtime — callers stay
 * responsible for matching the ``T`` shape to the documented response
 * model in the corresponding ``web/models/*.py`` Pydantic class.
 */
export async function getJson<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const url = options.query ? `${path}?${buildQuery(options.query)}` : path;
  const response = await fetch(url, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal: options.signal,
  });
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    const body = await safeReadBody(response);
    throw new ApiError(
      response.status,
      body,
      `GET ${path} → ${response.status} ${response.statusText}`,
    );
  }
  return (await response.json()) as T;
}

/**
 * Issue a POST against ``path`` with a JSON body, decode the JSON
 * response, and return it cast to ``T``. Mirrors :func:`getJson`'s
 * error contract: a non-2xx response throws an :class:`ApiError`
 * carrying the status + parsed body. Used by the ``/api/routing/preview``
 * client (item 2.4 — the new-session dialog's reactive preview is
 * the only POST surface that fits the typed-fetch wrapper's read-a-
 * JSON-body shape; the prompt endpoint and other write surfaces are
 * built on dedicated modules with their own retry / streaming logic).
 */
export async function postJson<T>(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = options.query ? `${path}?${buildQuery(options.query)}` : path;
  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
    signal: options.signal,
  });
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    const errorBody = await safeReadBody(response);
    throw new ApiError(
      response.status,
      errorBody,
      `POST ${path} → ${response.status} ${response.statusText}`,
    );
  }
  return (await response.json()) as T;
}

/**
 * Issue a PATCH against ``path`` with a JSON body, decode the JSON
 * response, and return it cast to ``T``. Mirrors :func:`postJson`'s
 * error contract. Used by the routing-rule editor (item 2.8) for the
 * ``PATCH /api/routing/{id}`` + ``PATCH /api/routing/system/{id}`` +
 * ``PATCH /api/tags/{id}/routing/reorder`` surfaces — all spec §9.
 *
 * Empty 204 responses are returned as ``undefined`` (cast to ``T``);
 * callers that need a body should not type ``T`` as ``void``. The
 * routing CRUD callers always type the response shape.
 */
export async function patchJson<T>(
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  return await sendJson<T>("PATCH", path, body, options);
}

/**
 * Issue a DELETE against ``path``. The 204-no-content path returns
 * ``undefined`` cast to ``T``; callers that expect ``void`` should
 * type the call as ``deleteResource<void>(...)``.
 */
export async function deleteResource<T = void>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  return await sendJson<T>("DELETE", path, null, options);
}

async function sendJson<T>(
  method: "PATCH" | "DELETE",
  path: string,
  body: unknown,
  options: RequestOptions = {},
): Promise<T> {
  const url = options.query ? `${path}?${buildQuery(options.query)}` : path;
  const init: RequestInit = {
    method,
    headers: { Accept: "application/json" },
    signal: options.signal,
  };
  if (body !== null && body !== undefined) {
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
    init.body = JSON.stringify(body);
  }
  const response = await fetch(url, init);
  if (response.status < HTTP_OK_MIN || response.status >= HTTP_OK_MAX) {
    const errBody = await safeReadBody(response);
    throw new ApiError(
      response.status,
      errBody,
      `${method} ${path} → ${response.status} ${response.statusText}`,
    );
  }
  if (response.status === HTTP_NO_CONTENT) {
    return undefined as T;
  }
  // Some PATCH endpoints return JSON; some DELETE endpoints return 204
  // with an empty body. Read the body once via ``text()`` and parse
  // only when present so the caller can use the typed return without
  // branching on the body length.
  const text = await response.text();
  if (text === "") {
    return undefined as T;
  }
  return JSON.parse(text) as T;
}

const HTTP_NO_CONTENT = 204;

function buildQuery(entries: Iterable<readonly [string, string]>): string {
  const params = new URLSearchParams();
  for (const [key, value] of entries) {
    params.append(key, value);
  }
  return params.toString();
}

async function safeReadBody(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    // Some endpoints return non-JSON 5xx pages; surface the text
    // rather than swallowing the failure.
    try {
      return await response.text();
    } catch {
      return null;
    }
  }
}
