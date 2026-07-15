<script setup lang="ts">
// Spotify's branding guide requires every displayed Spotify metadata item to
// link back to the service and permits this exact CTA. The official logo asset
// is intentionally not recreated here; release evidence records the remaining
// brand-asset gate separately.
import { computed, ref } from 'vue'

import { spotifyUrl } from '../lib/spotify'
import { openExternal } from '../shell'

const props = defineProps<{ kind: 'playlist' | 'track'; spotifyId: string; compact?: boolean }>()
const failed = ref(false)
const url = computed(() => spotifyUrl(props.kind, props.spotifyId))

async function open() {
  failed.value = false
  try {
    await openExternal(url.value)
  } catch {
    failed.value = true
  }
}
</script>

<template>
  <button
    type="button"
    class="spotify-attribution"
    :data-compact="compact || undefined"
    :data-failed="failed || undefined"
    :title="failed ? 'Spotify could not be opened' : 'Open this item in Spotify'"
    @click.stop="open"
  >
    OPEN SPOTIFY ↗
  </button>
</template>

<style scoped>
.spotify-attribution {
  flex: none;
  border: 1px solid rgba(255, 255, 255, 0.24);
  border-radius: 999px;
  background: #191414;
  color: #fff;
  padding: 4px 8px;
  font: 600 10px/1.2 Arial, sans-serif;
  letter-spacing: 0.03em;
  white-space: nowrap;
  cursor: pointer;
}
.spotify-attribution[data-compact='true'] {
  padding: 3px 6px;
  font-size: 9px;
}
.spotify-attribution[data-failed='true'] {
  border-color: var(--danger-border);
  color: var(--danger-text);
}
</style>
