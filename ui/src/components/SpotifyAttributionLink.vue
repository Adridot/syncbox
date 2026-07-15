<script setup lang="ts">
// Spotify's branding guide requires every displayed Spotify metadata item to
// link back to the service. Rendered as a discreet ↗ icon (localized
// tooltip) revealed on row hover — containers opt in with the global
// `hover-reveal` class. Opens the installed Spotify desktop app when
// present, the web player otherwise (owner decision 15/07).
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { spotifyAppUri, spotifyUrl } from '../lib/spotify'
import { openSpotify } from '../shell'

const props = defineProps<{ kind: 'playlist' | 'track'; spotifyId: string }>()
const { t } = useI18n()
const failed = ref(false)

async function open() {
  failed.value = false
  try {
    await openSpotify(
      spotifyAppUri(props.kind, props.spotifyId),
      spotifyUrl(props.kind, props.spotifyId),
    )
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <button
    type="button"
    class="spotify-attribution"
    :data-failed="failed || undefined"
    :title="failed ? t('spotify.openFailed') : t('spotify.open')"
    :aria-label="t('spotify.open')"
    @click.stop="open"
  >
    <svg
      class="ic"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      stroke-width="2"
      stroke-linecap="round"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </svg>
  </button>
</template>

<style scoped>
.spotify-attribution {
  flex: none;
  width: 22px;
  height: 22px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-muted);
  padding: 0;
  cursor: pointer;
  transition: opacity 120ms ease, color 120ms ease;
}
.spotify-attribution .ic {
  width: 13px;
  height: 13px;
}
.spotify-attribution:hover {
  color: #1db954; /* Spotify green — signals the destination */
  background: rgba(29, 185, 84, 0.1);
}
.spotify-attribution[data-failed='true'] {
  color: var(--danger-text);
}
/* revealed on hover/focus only inside opted-in containers */
:global(.hover-reveal .spotify-attribution) {
  opacity: 0;
}
:global(.hover-reveal:hover .spotify-attribution),
:global(.hover-reveal:focus-within .spotify-attribution) {
  opacity: 1;
}
</style>
