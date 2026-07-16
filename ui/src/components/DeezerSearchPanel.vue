<script setup lang="ts">
// Manual Deezer search (owner request 16/07, modeled on the previous
// Syncbox): slide-in panel prefilled with "artist title", results with
// cover + clickable 30 s preview so the pick can be verified by ear.
import { onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { DeezerSearchResult } from '../api/types'
import { useAudioPreview } from '../lib/audioPreview'

const props = defineProps<{ initialQuery: string; contextLabel?: string }>()
const emit = defineEmits<{ close: []; pick: [result: DeezerSearchResult] }>()
const { t } = useI18n()
const { playingId, toggle, stop } = useAudioPreview()

const query = ref(props.initialQuery)
const results = ref<DeezerSearchResult[] | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)

async function search() {
  const value = query.value.trim()
  if (!value) return
  busy.value = true
  error.value = null
  try {
    results.value = (
      await api.get<{ results: DeezerSearchResult[] }>(
        `/api/acquisition/deezer/search?q=${encodeURIComponent(value)}`,
      )
    ).results
  } catch (cause) {
    error.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    busy.value = false
  }
}
onMounted(() => void search())
onUnmounted(stop)

function pick(result: DeezerSearchResult) {
  stop()
  emit('pick', result)
}

function durationLabel(seconds: number | null): string {
  if (!seconds) return ''
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
</script>

<template>
  <aside class="panel" role="dialog" :aria-label="t('deezer.panelTitle')">
    <header class="panel-head">
      <div>
        <div class="panel-title">{{ t('deezer.panelTitle') }}</div>
        <div v-if="contextLabel" class="panel-context">
          {{ t('deezer.trackContext', { track: contextLabel }) }}
        </div>
      </div>
      <button class="panel-close" :aria-label="t('common.close')" @click="emit('close')">
        ✕
      </button>
    </header>

    <form class="search-row" @submit.prevent="search">
      <input
        v-model="query"
        type="text"
        class="search-input"
        :placeholder="t('deezer.placeholder')"
      />
      <button class="btn-primary search-btn" type="submit" :disabled="busy">
        {{ busy ? t('deezer.searching') : t('deezer.searchCta') }}
      </button>
    </form>

    <div v-if="error" class="panel-error">{{ error }}</div>

    <div class="results">
      <div v-for="result in results ?? []" :key="result.id" class="result">
        <span class="cover-wrap">
          <img v-if="result.cover_url" class="cover" :src="result.cover_url" alt="" />
          <span v-else class="cover cover-empty" />
          <button
            v-if="result.preview_url"
            class="play"
            :data-playing="playingId === result.id"
            :aria-label="playingId === result.id ? t('deezer.pause') : t('deezer.play')"
            @click="toggle(result.id, result.preview_url)"
          >
            {{ playingId === result.id ? '❚❚' : '▶' }}
          </button>
        </span>
        <span class="result-text">
          <span class="result-title">{{ result.title }}</span>
          <span class="result-sub">
            {{ result.artist
            }}<template v-if="result.album"> · {{ result.album }}</template>
            <template v-if="result.duration"> · {{ durationLabel(result.duration) }}</template>
          </span>
        </span>
        <button class="dl" @click="pick(result)">{{ t('deezer.download') }}</button>
      </div>
      <div v-if="results && !results.length && !busy" class="results-empty">
        {{ t('deezer.empty') }}
      </div>
    </div>
  </aside>
</template>

<style scoped>
.panel {
  position: fixed;
  top: 0;
  right: 0;
  bottom: 0;
  width: 420px;
  max-width: 90vw;
  z-index: 30;
  display: flex;
  flex-direction: column;
  background: var(--surface-raised);
  border-left: 1px solid var(--border-2);
  box-shadow: -14px 0 44px rgba(0, 0, 0, 0.5);
}
.panel-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid var(--border-subtle);
}
.panel-title {
  font-size: 14.5px;
  font-weight: 600;
}
.panel-context {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.panel-close {
  margin-left: auto;
  background: transparent;
  border: none;
  color: var(--text-secondary);
  font-size: 14px;
  cursor: pointer;
  padding: 2px 4px;
}
.search-row {
  display: flex;
  gap: 8px;
  padding: 14px 18px;
}
.search-input {
  flex: 1;
  min-width: 0;
}
.search-btn {
  white-space: nowrap;
}
.panel-error {
  margin: 0 18px 10px;
  padding: 8px 11px;
  border-radius: 8px;
  font-size: 12.5px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  color: var(--danger-text);
}
.results {
  flex: 1;
  overflow-y: auto;
  padding: 0 10px 14px;
}
.result {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 9px 8px;
  border-radius: 9px;
}
.result:hover {
  background: rgba(255, 255, 255, 0.03);
}
.cover-wrap {
  position: relative;
  width: 48px;
  height: 48px;
  flex: none;
}
.cover {
  width: 48px;
  height: 48px;
  border-radius: 7px;
  object-fit: cover;
  display: block;
}
.cover-empty {
  background: var(--surface);
  border: 1px solid var(--border-subtle);
}
.play {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  border: none;
  border-radius: 7px;
  background: rgba(0, 0, 0, 0.45);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.12s ease;
}
.cover-wrap:hover .play,
.play[data-playing='true'] {
  opacity: 1;
}
.result-text {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.result-title {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.result-sub {
  font-size: 11.5px;
  color: var(--text-muted-bright);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.dl {
  flex: none;
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  padding: 5px 11px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.results-empty {
  padding: 26px 8px;
  text-align: center;
  font-size: 12.5px;
  color: var(--text-muted);
}
</style>
