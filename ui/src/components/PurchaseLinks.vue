<script setup lang="ts">
// PurchaseLinks (SPEC-DESIGN §6, SPEC-UNIFIED §5.13/§6.5): the legal path,
// front and center. Beatport/Bandcamp search URLs built server-side; open
// in the system browser via the opener plugin (never target=_blank in a
// webview). The sidecar filters links out for removed_from_source — the UI
// must NOT re-add them.
import { openExternal } from '../shell'

defineProps<{ links: Array<{ store: string; url: string }> }>()
</script>

<template>
  <span class="links">
    <button v-for="link in links" :key="link.store" class="buy" @click="openExternal(link.url)">
      {{ link.store }}
    </button>
  </span>
</template>

<style scoped>
.links {
  display: inline-flex;
  gap: 6px;
}
.buy {
  background: var(--teal-tint);
  border: 1px solid var(--teal-border);
  color: var(--teal);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
</style>
