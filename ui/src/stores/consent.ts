/* Global consent broker for the 428 loop (M4-PLAN §4). The api client calls
   request() when a mutation returns consent_required; App.vue renders the
   matching modal (AnlzReplaceModal / IrreversibleDeleteModal) bound to this
   store, and the modal resolves the head of the queue. Consent is per-call,
   never remembered — request() always starts a fresh prompt.

   Concurrent 428s are QUEUED (FIFO): if two mutations both hit 428 before
   either is answered, each gets its own modal in turn. Overwriting a single
   `pending` slot would strand the first promise -> its mutation's in-flight
   counter never decrements -> jobRunning stuck true (found in M4.13 review). */

import { defineStore } from 'pinia'

import type { ApiErrorBody } from '../api/client'

interface PendingConsent {
  kind: 'anlz' | 'permanent_delete'
  path?: string
  message: string
  resolve: (granted: boolean) => void
}

export const useConsentStore = defineStore('consent', {
  state: () => ({
    queue: [] as PendingConsent[],
  }),
  getters: {
    pending: (state): PendingConsent | null => state.queue[0] ?? null,
  },
  actions: {
    request(body: ApiErrorBody): Promise<boolean> {
      return new Promise((resolve) => {
        this.queue.push({
          kind: body.consent as 'anlz' | 'permanent_delete',
          path: body.path,
          message: body.message,
          resolve,
        })
      })
    },
    grant() {
      this.queue.shift()?.resolve(true)
    },
    deny() {
      this.queue.shift()?.resolve(false)
    },
  },
})
