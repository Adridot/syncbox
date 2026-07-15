/* Spotify connect flow: authorize URL -> system browser -> poll /api/status
   until the callback lands. The poll is BOUNDED and CANCELS ON UNMOUNT
   (REMARKS: register the cancel in setup, never inside the async handler). */

import { onBeforeUnmount, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api, ApiError } from '../api/client'
import { openExternal } from '../shell'
import { useStatusStore } from '../stores/status'

export function useSpotifyConnect() {
  const { t } = useI18n()
  const status = useStatusStore()
  const connecting = ref(false)
  const error = ref<string | null>(null)
  let cancelled = false
  onBeforeUnmount(() => {
    cancelled = true
  })

  async function connect() {
    connecting.value = true
    error.value = null
    try {
      const { url } = await api.get<{ url: string }>('/api/spotify/authorize')
      await openExternal(url)
      await status.refresh()
      for (
        let attempt = 0;
        attempt < 60 && !cancelled && status.spotifyAuthorizationPending;
        attempt++
      ) {
        await new Promise((resolve) => setTimeout(resolve, 2000))
        await status.refresh()
      }
      if (!cancelled && status.spotifyAuthorizationResult !== 'ok')
        error.value = t(
          status.spotifyAuthorizationResult === 'error'
            ? 'settings.spotify.authorizationFailed'
            : 'settings.spotify.timeout',
        )
    } catch (cause) {
      // B1: a click must never be a silent no-op
      error.value =
        cause instanceof ApiError && cause.code === 'oauth_callback_port_in_use'
          ? t('settings.spotify.callbackPortInUse')
          : cause instanceof Error
            ? cause.message
            : String(cause)
    } finally {
      connecting.value = false
    }
  }

  return { connecting, error, connect }
}
