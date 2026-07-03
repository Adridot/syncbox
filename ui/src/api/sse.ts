/* ONE SSE client (M4-PLAN §4): a single EventSource on the canonical
   /events stream. Reconnection is native to EventSource; comment keepalives
   never reach the handlers (spec behavior). There is no job.error event and
   no replay after reconnect — SSE is progress DECORATION, the HTTP response
   is the authority — so the consumer clears its active jobs on (re)open. */

import { BASE_URL } from './client'

export interface JobProgressEvent {
  job: string
  kind: string
  done: number
  total: number
  pct: number
}

export interface JobDoneEvent {
  job: string
  kind: string
  [summary: string]: unknown
}

export interface JobStreamHandlers {
  onProgress?: (event: JobProgressEvent) => void
  onDone?: (event: JobDoneEvent) => void
  /** fired on every (re)connect — stale active jobs must be dropped */
  onOpen?: () => void
  /** connection lost; EventSource retries on its own */
  onError?: () => void
}

type EventSourceLike = {
  addEventListener(type: string, listener: (event: unknown) => void): void
  close(): void
  onopen: ((ev: unknown) => void) | null
  onerror: ((ev: unknown) => void) | null
}

export function connectJobStream(
  handlers: JobStreamHandlers,
  makeSource: (url: string) => EventSourceLike = (url) =>
    new EventSource(url) as unknown as EventSourceLike,
): () => void {
  const source = makeSource(`${BASE_URL}/events`)
  const parse = <T>(raw: unknown, deliver: (event: T) => void) => {
    try {
      deliver(JSON.parse((raw as MessageEvent).data) as T)
    } catch {
      /* a malformed frame must never kill the stream */
    }
  }
  source.addEventListener('job.progress', (event) =>
    parse<JobProgressEvent>(event, (parsed) => handlers.onProgress?.(parsed)),
  )
  source.addEventListener('job.done', (event) =>
    parse<JobDoneEvent>(event, (parsed) => handlers.onDone?.(parsed)),
  )
  source.onopen = () => handlers.onOpen?.()
  source.onerror = () => handlers.onError?.()
  return () => source.close()
}
