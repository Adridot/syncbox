<script setup lang="ts">
// Add-source flow (SPEC-DESIGN §6 + R5): paste a Spotify link (G5 resolved
// preview) OR pick from the connected account's playlists. Spotify-only —
// the mockup's Deezer half is deprecated (§11.1). Every failure path is
// surfaced actionably (B1): invalid link, private playlist (502/404),
// account not connected (409), duplicate follow (400).
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import type { MyTag, PlaylistPreview, Source, SpotifyPlaylist } from '../api/types'
import { extractPlaylistId } from '../lib/spotify'
import { useSpotifyConnect } from '../lib/useSpotifyConnect'
import { useStatusStore } from '../stores/status'
import ModalShell from './ModalShell.vue'
import SpotifyAttributionLink from './SpotifyAttributionLink.vue'
import TagSearchInput from './TagSearchInput.vue'

const props = defineProps<{ followedIds?: string[] }>()
const emit = defineEmits<{ close: []; added: [source: Source] }>()
const { t } = useI18n()
const status = useStatusStore()
const spotify = useSpotifyConnect()

// "Ma bibliothèque Spotify" is the default entry point (owner feedback
// 07/07); link-paste stays one click away and covers the not-connected case.
const mode = ref<'link' | 'picker'>('picker')
const link = ref('')
const preview = ref<PlaylistPreview | null>(null)
const previewLoading = ref(false)
const previewError = ref<{ text: string; connect?: boolean } | null>(null)

const playlists = ref<SpotifyPlaylist[] | null>(null)
const pickerError = ref<{ text: string; connect?: boolean } | null>(null)
const pickerLoading = ref(false)
const pickerQuery = ref('')
const picked = ref<SpotifyPlaylist | null>(null)

const tags = ref<string[]>([])
const catalog = ref<MyTag[]>([])
const following = ref(false)
const followError = ref<string | null>(null)

const playlistId = computed(() =>
  mode.value === 'link' ? extractPlaylistId(link.value) : (picked.value?.spotify_playlist_id ?? null),
)
const resolved = computed(() => (mode.value === 'link' ? preview.value : picked.value))
const canFollow = computed(() => Boolean(playlistId.value && resolved.value) && !following.value)

function describeError(cause: unknown): { text: string; connect?: boolean } {
  if (cause instanceof ApiError) {
    if (cause.code === 'spotify_not_connected')
      return { text: t('library.add.notConnected'), connect: true }
    if (cause.code === 'spotify_api_error' && cause.body.status_code === 404)
      return { text: t('library.add.privatePlaylist'), connect: true }
    return { text: cause.message }
  }
  return { text: t('common.networkError') }
}

let previewToken = 0
async function resolvePreview() {
  preview.value = null
  previewError.value = null
  if (mode.value !== 'link') return
  const id = playlistId.value
  if (!id) {
    if (link.value.trim()) previewError.value = { text: t('library.add.invalidLink') }
    return
  }
  const token = ++previewToken
  previewLoading.value = true
  try {
    const body = await api.get<PlaylistPreview>(`/api/spotify/playlists/${id}/preview`)
    if (token === previewToken) preview.value = body
  } catch (cause) {
    if (token === previewToken) previewError.value = describeError(cause)
  } finally {
    if (token === previewToken) previewLoading.value = false
  }
}
watch([link, mode], () => void resolvePreview())

async function loadPlaylists() {
  pickerLoading.value = true
  pickerError.value = null
  try {
    const body = await api.get<{ playlists: SpotifyPlaylist[] }>('/api/spotify/playlists')
    playlists.value = body.playlists
  } catch (cause) {
    pickerError.value = describeError(cause)
  } finally {
    pickerLoading.value = false
  }
}

watch(mode, () => {
  if (mode.value === 'picker' && playlists.value === null && !pickerLoading.value)
    void loadPlaylists()
})

const filteredPlaylists = computed(() => {
  const q = pickerQuery.value.trim().toLowerCase()
  const followed = new Set(props.followedIds ?? [])
  // already-followed playlists are hidden — they cannot be re-added anyway
  const list = (playlists.value ?? []).filter((p) => !followed.has(p.spotify_playlist_id))
  return q ? list.filter((p) => p.name.toLowerCase().includes(q)) : list
})

onMounted(async () => {
  if (mode.value === 'picker') void loadPlaylists()
  try {
    catalog.value = (await api.get<{ tags: MyTag[] }>('/api/mytags')).tags
  } catch {
    /* optional suggestions — free-text tag entry still works */
  }
})

function addTag(name: string) {
  if (!tags.value.includes(name)) tags.value.push(name)
}

async function follow() {
  if (!playlistId.value) return
  following.value = true
  followError.value = null
  try {
    const source = await api.post<Source>('/api/sources', {
      spotify_playlist_id: playlistId.value,
      name: resolved.value?.name ?? '',
      tags: tags.value,
      cover_url: resolved.value?.image_url ?? null,
    })
    emit('added', source)
  } catch (cause) {
    followError.value = cause instanceof ApiError ? cause.message : t('common.networkError')
  } finally {
    following.value = false
  }
}

async function connect() {
  await spotify.connect()
  if (status.spotifyConnected) {
    if (mode.value === 'picker') void loadPlaylists()
    else void resolvePreview()
  }
}
</script>

<template>
  <ModalShell width="600px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('library.add.title') }}</h3>
      <p class="sub">{{ t('library.add.sub') }}</p>

      <div class="modes">
        <button class="mode" :data-active="mode === 'picker'" @click="mode = 'picker'">
          {{ t('library.add.modePicker') }}
        </button>
        <button class="mode" :data-active="mode === 'link'" @click="mode = 'link'">
          {{ t('library.add.modeLink') }}
        </button>
      </div>

      <template v-if="mode === 'link'">
        <div class="link-row">
          <span class="glyph">🔗</span>
          <input
            v-model="link"
            type="text"
            class="mono"
            :placeholder="t('library.add.linkPlaceholder')"
          />
        </div>
        <div v-if="previewLoading" class="hint">{{ t('library.add.resolving') }}</div>
      </template>

      <template v-else>
        <div class="link-row">
          <span class="glyph">⌕</span>
          <input v-model="pickerQuery" type="text" :placeholder="t('library.add.pickerSearch')" />
        </div>
        <div v-if="pickerLoading" class="hint">{{ t('common.loading') }}</div>
        <div v-else-if="playlists" class="picker-list">
          <div
            v-for="playlist in filteredPlaylists"
            :key="playlist.spotify_playlist_id"
            class="picker-entry hover-reveal"
          >
            <button
              class="picker-row"
              :data-active="picked?.spotify_playlist_id === playlist.spotify_playlist_id"
              @click="picked = playlist"
            >
              <img
                v-if="playlist.image_url"
                class="cover art"
                :src="playlist.image_url"
                alt=""
                loading="lazy"
              />
              <span v-else class="cover">{{
                (playlist.name || '?').slice(0, 1).toUpperCase()
              }}</span>
              <span class="picker-text">
                <span class="picker-name">{{ playlist.name }}</span>
                <span class="picker-meta mono"
                  >{{ t('library.add.tracksUnit', { n: playlist.tracks_total }) }}<template
                    v-if="playlist.owner"
                  >
                    · {{ playlist.owner }}</template
                  ></span
                >
              </span>
            </button>
            <SpotifyAttributionLink
              kind="playlist"
              :spotify-id="playlist.spotify_playlist_id"
            />
          </div>
          <div v-if="!filteredPlaylists.length" class="hint">
            {{ t('library.add.pickerEmpty') }}
          </div>
        </div>
      </template>

      <!-- actionable errors (B1) -->
      <div v-if="mode === 'link' && previewError" class="error-row">
        <span>{{ previewError.text }}</span>
        <button v-if="previewError.connect" class="btn-secondary small" @click="connect">
          {{ t('library.add.connectCta') }}
        </button>
      </div>
      <div v-if="mode === 'picker' && pickerError" class="error-row">
        <span>{{ pickerError.text }}</span>
        <button v-if="pickerError.connect" class="btn-secondary small" @click="connect">
          {{ t('library.add.connectCta') }}
        </button>
      </div>
      <div v-if="spotify.error.value" class="error-row">{{ spotify.error.value }}</div>

      <!-- resolved preview -->
      <div v-if="resolved" class="preview hover-reveal">
        <img v-if="resolved.image_url" class="art" :src="resolved.image_url" alt="" />
        <span v-else class="art initial">{{ (resolved.name || '?').slice(0, 1).toUpperCase() }}</span>
        <div class="preview-text">
          <div class="preview-name">{{ resolved.name }}</div>
          <div class="preview-meta">
            <span class="mono">{{ t('library.add.tracksUnit', { n: resolved.tracks_total }) }}</span>
            <template v-if="resolved.owner">· {{ resolved.owner }}</template> · Spotify
          </div>
        </div>
        <SpotifyAttributionLink
          kind="playlist"
          :spotify-id="playlistId!"
        />
        <span class="resolved-tick">✓ {{ t('library.add.resolved') }}</span>
      </div>

      <!-- default MyTags -->
      <div class="tags-block">
        <div class="tags-label">{{ t('library.add.defaultTags') }}</div>
        <div class="chips">
          <button v-for="tag in tags" :key="tag" class="chip" @click="tags = tags.filter((x) => x !== tag)">
            {{ tag }} ✕
          </button>
          <TagSearchInput :catalog="catalog" :exclude="tags" @pick="addTag" />
        </div>
      </div>

      <div v-if="followError" class="error-row">{{ followError }}</div>

      <div class="actions">
        <button class="btn-secondary" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn-primary" :disabled="!canFollow" @click="follow">
          {{ following ? t('library.add.following') : t('library.add.follow') }}
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
.link-row {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 9px;
  padding: 9px 12px;
  margin-top: 15px;
}
.link-row .glyph {
  color: var(--text-muted);
  font-size: 14px;
}
.link-row input {
  flex: 1;
  min-width: 0;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: inherit;
  font-size: 12.5px;
}
.link-row input.mono {
  font-family: var(--font-mono);
}
.hint {
  color: var(--text-muted);
  font-size: 12px;
  margin-top: 10px;
}
.picker-list {
  margin-top: 10px;
  max-height: 240px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 6px;
  background: var(--surface);
}
.picker-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 7px 9px;
  border-radius: 8px;
  border: 1px solid transparent;
  background: transparent;
  cursor: pointer;
  text-align: left;
  color: inherit;
  flex: 1;
  min-width: 0;
}
.picker-entry {
  display: flex;
  align-items: center;
  gap: 6px;
}
.picker-row:hover {
  background: var(--surface-raised);
}
.picker-row[data-active='true'] {
  background: var(--accent-tint);
  border-color: var(--accent-border);
}
.cover {
  width: 30px;
  height: 30px;
  flex: none;
  border-radius: 7px;
  background: linear-gradient(135deg, var(--accent), var(--teal));
  display: grid;
  place-content: center;
  font-size: 13px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
}
.cover.art {
  object-fit: contain;
  background: var(--surface-raised);
}
.picker-text {
  min-width: 0;
  display: flex;
  flex-direction: column;
}
.picker-name {
  font-size: 13px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.picker-meta {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.error-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-top: 12px;
  background: var(--danger-tint);
  border: 1px solid var(--danger-border);
  border-radius: 9px;
  padding: 9px 12px;
  color: var(--danger-text);
  font-size: 12.5px;
}
.btn-secondary.small {
  padding: 5px 10px;
  font-size: 12px;
}
.preview {
  display: flex;
  align-items: center;
  gap: 13px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 11px;
  padding: 13px;
  margin-top: 13px;
}
.art {
  width: 52px;
  height: 52px;
  flex: none;
  border-radius: 9px;
  object-fit: contain;
}
.art.initial {
  background: linear-gradient(135deg, #1db954, var(--teal));
  display: grid;
  place-content: center;
  font-size: 20px;
  font-weight: 700;
  color: rgba(255, 255, 255, 0.92);
}
.preview-text {
  flex: 1;
  min-width: 0;
}
.preview-name {
  font-size: 14px;
  font-weight: 600;
}
.preview-meta {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-top: 2px;
}
.resolved-tick {
  font-size: 11.5px;
  color: var(--success);
  font-weight: 600;
  white-space: nowrap;
}
.tags-block {
  margin-top: 14px;
}
.tags-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 7px;
}
.chips {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  align-items: center;
}
.chip {
  background: var(--accent-tint);
  color: var(--accent-hover);
  border: 1px solid var(--accent-border);
  padding: 4px 10px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
}
.mono {
  font-family: var(--font-mono);
}
.actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 18px;
}
</style>
