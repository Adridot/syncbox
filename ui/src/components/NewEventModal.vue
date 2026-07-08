<script setup lang="ts">
// New event (§5.7, the 3 modes): from a FOLLOWED playlist (picker), from a
// Spotify link, or empty/manual — followed/link both resolve to the same
// spotify_playlist_id body (tracks imported at creation — owner-approved).
// The event name doubles as its 'Situation' MyTag. Spotify-only (§11.1).
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { EventSummary, Source } from '../api/types'
import { extractPlaylistId } from '../lib/spotify'
import ModalShell from './ModalShell.vue'

const emit = defineEmits<{ close: []; created: [event: EventSummary] }>()
const { t } = useI18n()

const mode = ref<'followed' | 'playlist' | 'empty'>('playlist')
const name = ref('')
const link = ref('')
const sources = ref<Source[]>([])
const followedId = ref('')
const creating = ref(false)
const error = ref<string | null>(null)

onMounted(async () => {
  try {
    sources.value = (await api.get<{ sources: Source[] }>('/api/sources')).sources
  } catch {
    /* the followed mode just shows its empty state */
  }
})

const playlistId = computed(() => extractPlaylistId(link.value))
const linkInvalid = computed(() => mode.value === 'playlist' && link.value.trim() !== '' && !playlistId.value)
const chosenPlaylistId = computed(() =>
  mode.value === 'followed' ? followedId.value || null : playlistId.value,
)
const canCreate = computed(
  () =>
    name.value.trim() !== '' &&
    !creating.value &&
    (mode.value === 'empty' || chosenPlaylistId.value !== null),
)

async function create() {
  creating.value = true
  error.value = null
  try {
    const body =
      mode.value === 'empty'
        ? { name: name.value.trim(), manual: true }
        : { name: name.value.trim(), spotify_playlist_id: chosenPlaylistId.value }
    emit('created', await api.post<EventSummary>('/api/events', body))
  } catch (cause) {
    // B1: creation failures (Spotify 409/502, slug issues) are surfaced
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <ModalShell width="560px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('events.new.title') }}</h3>
      <p class="sub">{{ t('events.new.sub') }}</p>

      <div class="modes">
        <button class="mode" :data-active="mode === 'followed'" @click="mode = 'followed'">
          {{ t('events.new.modeFollowed') }}
        </button>
        <button class="mode" :data-active="mode === 'playlist'" @click="mode = 'playlist'">
          {{ t('events.new.modePlaylist') }}
        </button>
        <button class="mode" :data-active="mode === 'empty'" @click="mode = 'empty'">
          {{ t('events.new.modeEmpty') }}
        </button>
      </div>

      <div class="field">
        <div class="label">{{ t('events.new.nameLabel') }}</div>
        <input v-model="name" type="text" :placeholder="t('events.new.namePlaceholder')" />
        <i18n-t tag="div" class="help" keypath="events.new.nameHelp">
          <template #category>
            <span class="mono">Situation</span>
          </template>
        </i18n-t>
      </div>

      <div v-if="mode === 'followed'" class="field">
        <div class="label">{{ t('events.new.followedLabel') }}</div>
        <select v-model="followedId" class="followed">
          <option value="" disabled>{{ t('events.new.followedPick') }}</option>
          <option v-for="s in sources" :key="s.id" :value="s.spotify_playlist_id">
            {{ s.name }}
          </option>
        </select>
        <div v-if="!sources.length" class="help">{{ t('events.new.followedEmpty') }}</div>
      </div>

      <div v-if="mode === 'playlist'" class="field">
        <div class="label">{{ t('events.new.linkLabel') }}</div>
        <div class="link-row">
          <span class="glyph">🔗</span>
          <input v-model="link" type="text" class="mono" :placeholder="t('events.new.linkPlaceholder')" />
        </div>
        <div class="help">{{ t('events.new.linkHelp') }}</div>
        <div v-if="linkInvalid" class="error-row">{{ t('library.add.invalidLink') }}</div>
      </div>

      <div v-if="error" class="error-row">{{ error }}</div>

      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn-primary" :disabled="!canCreate" @click="create">
          {{
            creating
              ? t('events.new.creating')
              : mode === 'empty'
                ? t('events.new.createEmpty')
                : t('events.new.createPlaylist')
          }}
        </button>
      </div>
    </div>
  </ModalShell>
</template>

<style scoped>
.body {
  padding: 22px;
}
h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0;
}
.sub {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
  line-height: 1.5;
}
.modes {
  display: flex;
  gap: 6px;
  margin-top: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 4px;
}
.mode {
  flex: 1;
  padding: 7px 10px;
  border-radius: 7px;
  border: 1px solid transparent;
  background: transparent;
  color: var(--text-muted-bright);
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.mode[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
}
.field {
  margin-top: 16px;
}
.label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.field > input,
.field > select {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-secondary-bright);
  font: inherit;
  font-size: 13px;
  outline: none;
  box-sizing: border-box;
}
.help {
  font-size: var(--size-meta);
  color: var(--text-muted);
  margin-top: 5px;
}
.link-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 9px 12px;
  min-width: 0;
}
.link-row .glyph {
  color: var(--text-muted);
  font-size: 13px;
}
.link-row input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-size: 12.5px;
}
.mono {
  font-family: var(--font-mono);
}
.error-row {
  margin-top: 12px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  border-radius: 9px;
  padding: 9px 12px;
  color: var(--danger-text);
  font-size: 12.5px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
</style>
