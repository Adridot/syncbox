/* ONE API client for the whole app (M4-PLAN §4) — types the sidecar error
   envelope as a discriminated union and centralizes the three interceptors:
   423 → notify the status store (rbOpen), 428 → ask the consent broker and
   re-call once with the consent flag, network failure → NetworkError so the
   backend-down surfaces can tell "down" from "refused". */

export const BASE_URL = 'http://127.0.0.1:8765'

export type ApiErrorCode =
  | 'mutation_blocked'
  | 'stale_snapshot'
  | 'conflict'
  | 'consent_required'
  | 'spotify_not_connected'
  | 'spotify_api_error'
  | 'not_found'
  | 'invalid_request'

export interface ApiErrorBody {
  error: ApiErrorCode
  message: string
  message_key?: string
  /** stale_snapshot: the sidecar guarantees nothing was written, no backup */
  action?: 'rerun_dry_run'
  consent?: 'anlz' | 'permanent_delete'
  path?: string
  /** spotify_api_error: the upstream Spotify status (404 = private playlist) */
  status_code?: number
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly body: ApiErrorBody,
  ) {
    super(body.message)
    this.name = 'ApiError'
  }

  get code(): ApiErrorCode {
    return this.body.error
  }
}

/** The sidecar is unreachable (connection refused / shell restarting). */
export class NetworkError extends Error {
  constructor(cause: unknown) {
    super('sidecar unreachable')
    this.name = 'NetworkError'
    this.cause = cause
  }
}

/** 428 consent loop: the UI registers a broker that shows the right modal
    (AnlzReplaceModal / IrreversibleDeleteModal) and resolves true when the
    user explicitly consents. Consent is per-call, never remembered — the
    flag is added to ONE re-call only. */
export type ConsentBroker = (body: ApiErrorBody) => Promise<boolean>
let consentBroker: ConsentBroker | null = null
export function setConsentBroker(broker: ConsentBroker | null): void {
  consentBroker = broker
}

const CONSENT_FLAG: Record<'anlz' | 'permanent_delete', string> = {
  anlz: 'anlz_consent',
  permanent_delete: 'consent_to_permanent_delete',
}

/** 423 interceptor: the status store registers itself here. */
let mutationBlockedHook: (() => void) | null = null
export function setMutationBlockedHook(hook: (() => void) | null): void {
  mutationBlockedHook = hook
}

/* In-flight mutation tracking: feeds the app-wide jobRunning flag (one lock
   sidecar-side — the UI must not fire parallel mutations). */
let inFlightMutations = 0
const inFlightWatchers = new Set<(count: number) => void>()
export function onInFlightMutations(watcher: (count: number) => void): () => void {
  inFlightWatchers.add(watcher)
  return () => inFlightWatchers.delete(watcher)
}
function setInFlight(count: number): void {
  inFlightMutations = count
  inFlightWatchers.forEach((watch) => watch(inFlightMutations))
}

async function doFetch<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers: body === undefined ? undefined : { 'content-type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (cause) {
    throw new NetworkError(cause)
  }
  if (response.ok) {
    return (await response.json()) as T
  }
  const errorBody = (await response.json().catch(() => ({
    error: 'invalid_request' as const,
    message: `HTTP ${response.status}`,
  }))) as ApiErrorBody
  if (response.status === 423) {
    mutationBlockedHook?.()
  }
  throw new ApiError(response.status, errorBody)
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const mutating = method !== 'GET'
  if (mutating) setInFlight(inFlightMutations + 1)
  try {
    try {
      return await doFetch<T>(method, path, body)
    } catch (error) {
      if (
        error instanceof ApiError &&
        error.status === 428 &&
        error.body.consent &&
        consentBroker
      ) {
        const granted = await consentBroker(error.body)
        if (granted) {
          const flag = CONSENT_FLAG[error.body.consent]
          return await doFetch<T>(method, path, { ...(body as object), [flag]: true })
        }
      }
      throw error
    }
  } finally {
    if (mutating) setInFlight(inFlightMutations - 1)
  }
}

export const api = {
  get: <T>(path: string) => request<T>('GET', path),
  post: <T>(path: string, body?: unknown) => request<T>('POST', path, body ?? {}),
  put: <T>(path: string, body: unknown) => request<T>('PUT', path, body),
  patch: <T>(path: string, body: unknown) => request<T>('PATCH', path, body),
  delete: <T>(path: string) => request<T>('DELETE', path),
}
