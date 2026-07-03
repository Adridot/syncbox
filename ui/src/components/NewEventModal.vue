<script setup lang="ts">
// NewEventModal (SPEC-DESIGN §2, §11.1): create an event from a Spotify
// playlist link or empty (manual). Deezer/SoundCloud modes are deprecated
// (M4-PLAN §6) — Spotify-only. The name doubles as the "Situation" MyTag.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/client'
import { extractPlaylistId } from '../lib/spotify-link'
import { useEventsStore } from '../stores/events'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const events = useEventsStore()
const emit = defineEmits<{ close: []; created: [number] }>()

const mode = ref<'playlist' | 'empty'>('playlist')
const name = ref('')
const playlistUrl = ref('')
const error = ref<string | null>(null)
const submitting = ref(false)

const playlistId = computed(() => extractPlaylistId(playlistUrl.value))
const canCreate = computed(
  () => name.value.trim().length > 0 && (mode.value === 'empty' || playlistId.value !== null),
)

async function create() {
  if (!canCreate.value) return
  submitting.value = true
  error.value = null
  try {
    const event = await events.createEvent(name.value.trim(), {
      spotify_playlist_id: mode.value === 'playlist' ? playlistId.value! : undefined,
      manual: mode.value === 'empty',
    })
    emit('created', event.id)
    emit('close')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('events.new.failed')
  } finally {
    submitting.value = false
  }
}
</script>

<template>
  <ModalShell width="480px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('events.new.title') }}</h3>
      <p class="lede">{{ t('events.new.lede') }}</p>

      <div class="tabs">
        <button class="tab" :data-active="mode === 'playlist'" @click="mode = 'playlist'">
          {{ t('events.new.fromPlaylist') }}
        </button>
        <button class="tab" :data-active="mode === 'empty'" @click="mode = 'empty'">
          {{ t('events.new.empty') }}
        </button>
      </div>

      <div class="field">
        <div class="field-label">{{ t('events.new.name') }}</div>
        <input v-model="name" class="input" :placeholder="t('events.new.namePlaceholder')" />
        <div class="hint">{{ t('events.new.nameHint') }}</div>
      </div>

      <div v-if="mode === 'playlist'" class="field">
        <div class="field-label">{{ t('events.new.playlistLink') }}</div>
        <div class="link-field">
          <span>🔗</span>
          <input v-model="playlistUrl" class="link-input" :placeholder="t('events.new.playlistPlaceholder')" />
        </div>
        <div class="hint">{{ t('events.new.playlistHint') }}</div>
      </div>
      <div v-else class="field">
        <div class="hint">{{ t('events.new.emptyHint') }}</div>
      </div>

      <div v-if="error" class="error-line">{{ error }}</div>

      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn-primary" :disabled="!canCreate || submitting" @click="create">
          {{ t('events.new.create') }}
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
.lede {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin: 5px 0 0;
  line-height: 1.5;
}
.tabs {
  display: flex;
  gap: 6px;
  margin-top: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 4px;
}
.tab {
  flex: 1;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  padding: 8px;
  border-radius: 7px;
  font-size: 12.5px;
  cursor: pointer;
}
.tab[data-active='true'] {
  background: var(--accent-tint);
  color: var(--accent-hover);
  font-weight: 600;
}
.field {
  margin-top: 16px;
}
.field-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 6px;
}
.input {
  width: 100%;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 13px;
  outline: none;
}
.hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 5px;
}
.link-field {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 8px;
  padding: 9px 12px;
  color: var(--text-muted);
}
.link-input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: var(--font-mono);
  font-size: 12.5px;
}
.error-line {
  color: var(--danger-text);
  font-size: 12.5px;
  margin-top: 12px;
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
.btn-ghost {
  background: #14171f;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 9px 16px;
  border-radius: 9px;
  font-size: 13px;
  cursor: pointer;
}
.btn-primary {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
.btn-primary:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
