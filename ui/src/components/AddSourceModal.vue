<script setup lang="ts">
// AddSourceModal (SPEC-DESIGN §6, G5): paste a Spotify link -> client-side
// id extraction -> read-only resolved preview (cover/name/tracks) -> follow
// with default MyTags. Spotify-only (no Deezer/SoundCloud parsing, §6).
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import { extractPlaylistId } from '../lib/spotify-link'
import { useLibraryStore } from '../stores/library'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const library = useLibraryStore()
const emit = defineEmits<{ close: []; added: [number] }>()

interface Preview {
  name: string | null
  owner: string | null
  tracks_total: number
  image_url: string | null
}

const link = ref('')
const preview = ref<Preview | null>(null)
const resolving = ref(false)
const error = ref<string | null>(null)
const tags = ref<string[]>([])
const newTag = ref('')
const following = ref(false)

const playlistId = computed(() => extractPlaylistId(link.value))

watch(playlistId, async (id) => {
  preview.value = null
  error.value = null
  if (!id) return
  resolving.value = true
  try {
    preview.value = await api.get<Preview>(`/api/spotify/playlists/${id}/preview`)
  } catch (err) {
    error.value =
      err instanceof ApiError && err.code === 'spotify_not_connected'
        ? t('library.addSource.notConnected')
        : t('library.addSource.resolveFailed')
  } finally {
    resolving.value = false
  }
})

function addTag() {
  const value = newTag.value.trim()
  if (value && !tags.value.includes(value)) tags.value.push(value)
  newTag.value = ''
}

async function follow() {
  if (!playlistId.value) return
  following.value = true
  try {
    const source = await library.addSource(
      playlistId.value,
      preview.value?.name ?? '',
      tags.value,
    )
    emit('added', source.id)
    emit('close')
  } catch (err) {
    error.value = err instanceof ApiError ? err.message : t('library.addSource.resolveFailed')
  } finally {
    following.value = false
  }
}
</script>

<template>
  <ModalShell width="520px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('library.addSource.title') }}</h3>
      <p class="lede">{{ t('library.addSource.lede') }}</p>

      <div class="link-field">
        <span class="glyph">🔗</span>
        <input
          v-model="link"
          type="text"
          class="link-input"
          :placeholder="t('library.addSource.placeholder')"
        />
      </div>

      <div v-if="resolving" class="resolving">{{ t('library.addSource.resolving') }}</div>
      <div v-else-if="error" class="error-line">{{ error }}</div>

      <div v-if="preview" class="preview">
        <img v-if="preview.image_url" :src="preview.image_url" class="cover" alt="" />
        <div v-else class="cover placeholder">{{ (preview.name ?? '?')[0] }}</div>
        <div class="preview-text">
          <div class="preview-name">{{ preview.name }}</div>
          <div class="preview-meta">
            <span class="mono">{{ preview.tracks_total }}</span> {{ t('library.addSource.tracks') }}
            <template v-if="preview.owner"> · {{ preview.owner }}</template> · Spotify
          </div>
        </div>
        <span class="resolved">✓ {{ t('library.addSource.resolved') }}</span>
      </div>

      <div v-if="preview" class="tags-block">
        <div class="tags-label">{{ t('library.addSource.defaultTags') }}</div>
        <div class="tags">
          <span v-for="tag in tags" :key="tag" class="chip" @click="tags = tags.filter((x) => x !== tag)"
            >{{ tag }} ✕</span
          >
          <input
            v-model="newTag"
            class="tag-input"
            :placeholder="t('library.addSource.addTag')"
            @keydown.enter.prevent="addTag"
          />
        </div>
      </div>

      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button class="btn-primary" :disabled="!preview || following" @click="follow">
          {{ t('library.addSource.follow') }}
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
.link-field {
  display: flex;
  align-items: center;
  gap: 8px;
  background: var(--surface-raised);
  border: 1px solid #2a3140;
  border-radius: 9px;
  padding: 9px 12px;
  margin-top: 15px;
}
.link-input {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  color: var(--text-secondary-bright);
  font-family: var(--font-mono);
  font-size: 12.5px;
}
.resolving,
.error-line {
  font-size: 12.5px;
  margin-top: 12px;
}
.resolving {
  color: var(--text-muted-bright);
}
.error-line {
  color: var(--danger-text);
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
.cover {
  width: 52px;
  height: 52px;
  flex: none;
  border-radius: 9px;
  object-fit: cover;
}
.cover.placeholder {
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
.mono {
  font-family: var(--font-mono);
}
.resolved {
  font-size: 11.5px;
  color: var(--success);
  font-weight: 600;
}
.tags-block {
  margin-top: 14px;
}
.tags-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 7px;
}
.tags {
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
}
.tag-input {
  background: transparent;
  border: 1px dashed #2a3140;
  color: var(--text-secondary);
  padding: 4px 10px;
  border-radius: 7px;
  font-size: 12px;
  outline: none;
  font-family: inherit;
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
