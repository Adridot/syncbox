<script setup lang="ts">
// Spotify's branding guide requires every displayed Spotify metadata item to
// link back to the service. Rendered as a discreet ↗ icon (localized
// tooltip) revealed on row hover — containers opt in with the global
// `hover-reveal` class. Opens the installed Spotify desktop app when
// present, the web player otherwise (owner decision 15/07).
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import {
  acquireHoverReveal,
  activeHoverReveal,
  releaseHoverReveal,
} from '../lib/hover-reveal'
import { spotifyAppUri, spotifyUrl } from '../lib/spotify'
import { openSpotify } from '../shell'

const props = defineProps<{ kind: 'playlist' | 'track'; spotifyId: string }>()
const { t } = useI18n()
const failed = ref(false)

// Reveal driven by the shared hover-reveal tracker (see lib/hover-reveal.ts)
// instead of CSS :hover — WKWebView ghost-hover bug. Hiding is STRUCTURAL
// (v-if on the icon, no opacity, no transition): opacity animations give
// each arrow its own compositing layer, and WKWebView orphans those layers
// when virtualized rows move or unmount mid-animation — the arrows' pixels
// then linger on screen with no DOM behind them. An icon that is not in
// the DOM cannot leave pixels. Keyboard focus inside the row still reveals
// (focusin/focusout below). Sites without a `.hover-reveal` ancestor
// (History, ReMatchModal) keep the arrow permanently visible.
const root = ref<HTMLElement | null>(null)
let container: Element | null = null
const permanentSite = ref(false)
const containerFocused = ref(false)
const revealed = computed(() => {
  // read the ref FIRST: short-circuiting past it on the initial evaluation
  // would leave the computed without its reactive dependency
  const active = activeHoverReveal.value
  return active !== null && active === container
})
const shown = computed(
  () => permanentSite.value || revealed.value || containerFocused.value,
)

const onFocusin = () => {
  containerFocused.value = true
}
const onFocusout = (event: Event) => {
  const next = (event as FocusEvent).relatedTarget
  containerFocused.value =
    next instanceof Node && container !== null && container.contains(next)
}

onMounted(() => {
  container = root.value?.closest('.hover-reveal') ?? null
  if (!container) {
    permanentSite.value = true
    return
  }
  acquireHoverReveal()
  container.addEventListener('focusin', onFocusin)
  container.addEventListener('focusout', onFocusout)
})

onBeforeUnmount(() => {
  if (!container) return
  container.removeEventListener('focusin', onFocusin)
  container.removeEventListener('focusout', onFocusout)
  releaseHoverReveal(container)
  container = null
})

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
    ref="root"
    type="button"
    class="spotify-attribution"
    :data-failed="failed || undefined"
    :data-shown="shown || undefined"
    :title="failed ? t('spotify.openFailed') : t('spotify.open')"
    :aria-label="t('spotify.open')"
    @click.stop="open"
  >
    <svg
      v-if="shown"
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
  transition: color 120ms ease;
}
.spotify-attribution .ic {
  width: 13px;
  height: 13px;
}
/* hover affordance only while the icon is shown — a ghost :hover on an
   empty button must not paint anything */
.spotify-attribution[data-shown]:hover {
  color: #1db954; /* Spotify green — signals the destination */
  background: rgba(29, 185, 84, 0.1);
}
.spotify-attribution[data-failed='true'] {
  color: var(--danger-text);
}
/* NO opacity/transition-based hiding here: the icon is structurally
   removed (v-if) when hidden — WKWebView orphans opacity-animation
   compositing layers during virtualized scrolling (ghost arrows) */
</style>
