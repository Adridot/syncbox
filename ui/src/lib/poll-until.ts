/* Bounded poll loop that auto-cancels when the calling component unmounts
   (M4.13 review: the Spotify OAuth completion loops kept running and could
   stack after navigate-away).

   Call useCancellablePoll() at setup top-level — it registers the unmount
   hook there (onScopeDispose only binds to the active setup scope, never to
   a later event handler). The returned poll() closure honors that flag. */

import { onScopeDispose } from 'vue'

export function useCancellablePoll() {
  let cancelled = false
  onScopeDispose(() => {
    cancelled = true
  })
  return function poll(
    done: () => boolean,
    step: () => Promise<void> | void,
    { attempts = 60, intervalMs = 2000 }: { attempts?: number; intervalMs?: number } = {},
  ): Promise<void> {
    return (async () => {
      for (let i = 0; i < attempts && !cancelled && !done(); i++) {
        await new Promise((resolve) => setTimeout(resolve, intervalMs))
        if (cancelled) return
        await step()
      }
    })()
  }
}
