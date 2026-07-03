<script setup lang="ts">
// Dashboard (SPEC-DESIGN §2 + SPEC-UNIFIED §11.3). Hero variants closed/
// open; 4 deep-link tiles reading the canonical health selector; snapshot
// card = the §11.3 readouts ONLY (mockup extras without an API source are
// not built); UI-local activity feed; connections panel. The deprecated
// "Module téléchargement" row and "Tout voir → Acquisition" are not built.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { NetworkError, api } from '../api/client'
import JobRow from '../components/JobRow.vue'
import LoadingState from '../components/LoadingState.vue'
import { useCancellablePoll } from '../lib/poll-until'
import { openExternal } from '../shell'
import { useHealthStore } from '../stores/health'
import { useJobsStore } from '../stores/jobs'
import { useSettingsStore } from '../stores/settings'
import { useStatusStore } from '../stores/status'

interface Readouts {
  total_tracks: number
  keys_analyzed: { total: number; analyzed: number; pct: number }
  never_played: number
  added_this_month: number
  last_import: string | null
  genres: Array<{ genre: string; count: number }>
  quality: { ok: number; lossy_source_probable: number; incertain: number }
}

const { t } = useI18n()
const router = useRouter()
const status = useStatusStore()
const health = useHealthStore()
const jobs = useJobsStore()
const settings = useSettingsStore()
const poll = useCancellablePoll()

const readouts = ref<Readouts | null>(null)
const lastBackup = ref<string | null>(null)
const sourcesCount = ref<number | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    if (!settings.loaded) await settings.load()
    if (settings.configured) {
      const [reads, backups, sources] = await Promise.all([
        api.get<Readouts>('/api/readouts'),
        api.get<{ backups: Array<{ name: string }> }>('/api/doctor/backups'),
        api.get<{ sources: unknown[] }>('/api/sources'),
      ])
      readouts.value = reads
      lastBackup.value = backups.backups[0]?.name ?? null
      sourcesCount.value = sources.sources.length
      void health.loadCounts().catch(() => {})
    }
  } catch (error) {
    if (!(error instanceof NetworkError)) console.error(error)
  } finally {
    loading.value = false
  }
})

const tiles = computed(() => [
  {
    key: 'sources',
    label: t('dashboard.tiles.sources'),
    value: sourcesCount.value,
    sub:
      health.badges.library !== null
        ? t('dashboard.tiles.toReview', { n: health.badges.library })
        : t('dashboard.tiles.openLibrary'),
    tone: 'accent',
    to: '/library',
  },
  {
    key: 'duplicates',
    label: t('dashboard.tiles.duplicates'),
    value: health.badges.duplicates,
    sub:
      health.badges.duplicates === null
        ? t('dashboard.tiles.runScan')
        : t('dashboard.tiles.groupsToConfirm'),
    tone: 'warning',
    to: '/health/duplicates',
  },
  {
    key: 'missing',
    label: t('dashboard.tiles.missing'),
    value: health.missingTotal,
    sub: t('dashboard.tiles.purchaseOrRelink'),
    tone: 'danger',
    to: '/missing',
  },
  {
    key: 'untagged',
    label: t('dashboard.tiles.untagged'),
    value: health.badges.untagged,
    sub: t('dashboard.tiles.smartFixes'),
    tone: 'teal',
    to: '/health/smartfixes',
  },
])

const backupLabel = computed(() => {
  if (!lastBackup.value) return t('dashboard.hero.noBackup')
  // rekordbox-db-YYYYMMDD-HHMMSS[-n] -> readable timestamp
  const match = lastBackup.value.match(/(\d{8})-(\d{6})/)
  if (!match) return lastBackup.value
  const [, day, time] = match
  return `${day.slice(6, 8)}/${day.slice(4, 6)}/${day.slice(0, 4)} ${time.slice(0, 2)}:${time.slice(2, 4)}`
})

const activity = computed(() =>
  [...jobs.doneLog]
    .reverse()
    .slice(0, 6)
    .map((entry) => ({
      key: `${entry.job}`,
      text: t(`activity.${entry.kind.replace('.', '_')}`, entry as never),
      time: new Date(entry.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
    })),
)

const syncing = computed(() => jobs.progressOf('sources.sync_all') !== null)

async function syncSources() {
  try {
    await api.post('/api/sources/sync')
    void health.loadCounts().catch(() => {})
  } catch {
    /* per-source errors are reported in the results; SSE decorates */
  }
}

async function connectSpotify() {
  const { url } = await api.get<{ url: string }>('/api/spotify/authorize')
  await openExternal(url)
  // the callback lands on the sidecar; poll status until it flips (auto-
  // cancels if the user navigates away before OAuth completes)
  await poll(() => status.spotifyConnected, () => status.refresh())
}
</script>

<template>
  <main class="screen">
    <header class="head">
      <div>
        <h1>{{ t('nav.dashboard') }}</h1>
        <p class="tagline">{{ t('dashboard.tagline') }}</p>
      </div>
      <div class="actions">
        <button
          class="btn-secondary"
          :disabled="jobs.jobRunning"
          @click="syncSources"
        >
          <span class="btn-icon">↻</span>{{ t('dashboard.syncSources') }}
        </button>
        <button class="btn-primary" @click="router.push('/events')">
          {{ t('dashboard.createEvent') }}
        </button>
      </div>
    </header>

    <LoadingState v-if="loading" :rows="4" />

    <template v-else-if="settings.configured">
      <!-- RB safety hero: closed/open variants (SPEC-DESIGN §3.5) -->
      <section class="hero" :data-open="status.rbOpen">
        <div class="hero-icon">{{ status.rbOpen ? '☕' : '✓' }}</div>
        <div class="hero-text">
          <div class="hero-title">
            {{ status.rbOpen ? t('dashboard.hero.openTitle') : t('dashboard.hero.closedTitle') }}
          </div>
          <div class="hero-sub">
            {{ status.rbOpen ? t('dashboard.hero.openSub') : t('dashboard.hero.closedSub') }}
          </div>
        </div>
        <div class="hero-backup">
          <div class="backup-label">{{ t('dashboard.hero.lastBackup') }}</div>
          <div class="backup-value">{{ backupLabel }}</div>
        </div>
      </section>

      <section class="tiles">
        <router-link v-for="tile in tiles" :key="tile.key" class="tile" :to="tile.to">
          <div class="tile-label">{{ tile.label }}</div>
          <div class="tile-value">{{ tile.value ?? '—' }}</div>
          <div class="tile-sub" :data-tone="tile.tone">{{ tile.sub }} →</div>
        </router-link>
      </section>

      <!-- Collection snapshot: §11.3 readouts, QualityBadge vocabulary,
           never a red binary counter -->
      <section v-if="readouts" class="card snapshot">
        <div class="card-head">
          <h3>{{ t('dashboard.snapshot.title') }}</h3>
          <span class="mono meta"
            >{{ readouts.total_tracks }} {{ t('dashboard.snapshot.tracks') }}</span
          >
        </div>
        <div class="readout-grid">
          <div>
            <div class="readout-label">{{ t('dashboard.snapshot.quality') }}</div>
            <div class="readout-main">
              <span class="mono big success">{{ readouts.quality.ok }}</span>
              <span class="readout-unit">{{ t('quality.ok') }}</span>
            </div>
            <div class="readout-rows">
              <div class="readout-row">
                <span class="mono warning-color">{{ readouts.quality.lossy_source_probable }}</span>
                <span>{{ t('quality.lossy_source_probable') }}</span>
              </div>
              <div class="readout-row">
                <span class="mono uncertain-color">{{ readouts.quality.incertain }}</span>
                <span>{{ t('quality.incertain') }}</span>
              </div>
            </div>
          </div>
          <div>
            <div class="readout-label">{{ t('dashboard.snapshot.setReady') }}</div>
            <div class="readout-main">
              <span class="mono big accent-color">{{ readouts.keys_analyzed.pct }}%</span>
              <span class="readout-unit">{{ t('dashboard.snapshot.camelotKey') }}</span>
            </div>
            <div class="readout-sub mono">{{ t('dashboard.snapshot.keysAnalyzed') }}</div>
          </div>
          <div>
            <div class="readout-label">{{ t('dashboard.snapshot.activity') }}</div>
            <div class="readout-main">
              <span class="mono big">+{{ readouts.added_this_month }}</span>
              <span class="readout-unit">{{ t('dashboard.snapshot.thisMonth') }}</span>
            </div>
            <div v-if="readouts.last_import" class="readout-sub mono">
              {{ t('dashboard.snapshot.lastImport') }} {{ readouts.last_import.slice(0, 10) }}
            </div>
            <div class="readout-rows">
              <div class="readout-row">
                <span class="mono uncertain-color">{{ readouts.never_played }}</span>
                <span>{{ t('dashboard.snapshot.neverPlayed') }}</span>
              </div>
            </div>
          </div>
        </div>
        <div v-if="readouts.genres.length" class="genres">
          <div class="readout-label">{{ t('dashboard.snapshot.genres') }}</div>
          <div class="genre-chips">
            <span v-for="genre in readouts.genres" :key="genre.genre" class="genre-chip">
              {{ genre.genre }} <span class="mono">{{ genre.count }}</span>
            </span>
          </div>
        </div>
      </section>

      <section class="columns">
        <div class="card">
          <div class="card-head">
            <h3>{{ t('dashboard.activity.title') }}</h3>
          </div>
          <JobRow kind="sources.sync_all" :label="t('activity.job_sources_sync_all')" />
          <JobRow kind="sources.sync" :label="t('activity.job_sources_sync')" />
          <div v-if="!activity.length && !syncing" class="feed-empty">
            {{ t('dashboard.activity.empty') }}
          </div>
          <div v-for="row in activity" :key="row.key" class="feed-row">
            <span class="feed-dot" />
            <span class="feed-text">{{ row.text }}</span>
            <span class="mono meta">{{ row.time }}</span>
          </div>
        </div>

        <div class="card">
          <div class="card-head">
            <h3>{{ t('dashboard.connections.title') }}</h3>
          </div>
          <div class="conn-row">
            <div class="conn-icon">♫</div>
            <div class="conn-text">
              <div class="conn-name">Spotify</div>
              <div class="mono meta">{{ t('dashboard.connections.spotifyMeta') }}</div>
            </div>
            <span class="conn-state" :data-ok="status.spotifyConnected">{{
              status.spotifyConnected ? t('chrome.connected') : t('chrome.notConnected')
            }}</span>
            <button v-if="!status.spotifyConnected" class="conn-action" @click="connectSpotify">
              {{ t('dashboard.connections.connect') }}
            </button>
          </div>
        </div>
      </section>
    </template>

    <section v-else class="card unconfigured">
      <h3>{{ t('dashboard.unconfigured.title') }}</h3>
      <p>{{ t('dashboard.unconfigured.body') }}</p>
      <router-link to="/settings" class="btn-primary">{{ t('nav.settings') }}</router-link>
    </section>
  </main>
</template>

<style scoped>
.screen {
  padding: var(--screen-padding);
  max-width: var(--content-max-width);
  margin: 0 auto;
}
.head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 24px;
}
h1 {
  font: var(--text-h1);
  letter-spacing: -0.02em;
  margin: 0;
}
.tagline {
  color: var(--text-muted-bright);
  font-size: 14px;
  margin: 4px 0 0;
}
.actions {
  display: flex;
  gap: 10px;
}
.btn-secondary {
  background: #14171f;
  border: 1px solid #2a3140;
  color: var(--text-secondary-bright);
  padding: 9px 15px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 7px;
  white-space: nowrap;
}
.btn-secondary:disabled {
  opacity: 0.55;
  cursor: default;
}
.btn-icon {
  color: var(--accent);
}
.btn-primary {
  background: var(--accent);
  border: 1px solid var(--accent);
  color: #06131f;
  padding: 9px 15px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  text-decoration: none;
  display: inline-block;
}
.hero {
  border-radius: var(--radius-card);
  padding: 18px 20px;
  margin-bottom: 22px;
  display: flex;
  align-items: center;
  gap: 16px;
  background: linear-gradient(100deg, rgba(52, 211, 153, 0.1), rgba(45, 212, 191, 0.04));
  border: 1px solid rgba(52, 211, 153, 0.22);
}
.hero[data-open='true'] {
  background: linear-gradient(100deg, rgba(245, 181, 68, 0.1), rgba(245, 181, 68, 0.03));
  border-color: rgba(245, 181, 68, 0.24);
}
.hero-icon {
  width: 42px;
  height: 42px;
  border-radius: 11px;
  background: rgba(52, 211, 153, 0.14);
  display: grid;
  place-content: center;
  font-size: 20px;
  flex: none;
}
.hero[data-open='true'] .hero-icon {
  background: rgba(245, 181, 68, 0.14);
}
.hero-text {
  flex: 1;
}
.hero-title {
  font-weight: 600;
  font-size: 15px;
  color: #5fe0b0;
}
.hero[data-open='true'] .hero-title {
  color: var(--warning-text);
}
.hero-sub {
  color: #8b97a9;
  font-size: 13px;
  margin-top: 2px;
}
.hero-backup {
  text-align: right;
  flex: none;
}
.backup-label {
  font-size: var(--size-meta);
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  white-space: nowrap;
}
.backup-value {
  font-family: var(--font-mono);
  font-size: 13px;
  color: var(--text-secondary-bright);
  margin-top: 3px;
  white-space: nowrap;
}
.tiles {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 22px;
}
.tile {
  background: var(--surface-raised);
  border: 1px solid var(--border-2);
  border-radius: 13px;
  padding: 16px;
  cursor: pointer;
  text-decoration: none;
  color: inherit;
  display: block;
}
.tile:hover {
  background: #141823;
  border-color: #2a3242;
}
.tile-label {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.tile-value {
  font-size: 28px;
  font-weight: 600;
  margin-top: 6px;
  letter-spacing: -0.02em;
}
.tile-sub {
  font-size: 12px;
  margin-top: 4px;
}
.tile-sub[data-tone='accent'] {
  color: var(--accent);
}
.tile-sub[data-tone='warning'] {
  color: var(--warning);
}
.tile-sub[data-tone='danger'] {
  color: var(--danger);
}
.tile-sub[data-tone='teal'] {
  color: var(--teal);
}
.card {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  padding: 18px;
  margin-bottom: 22px;
}
.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}
.card-head h3 {
  font: var(--text-h3);
  margin: 0;
}
.mono {
  font-family: var(--font-mono);
}
.meta {
  font-size: var(--size-meta);
  color: var(--text-muted);
}
.readout-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 20px;
}
.readout-label {
  font-size: var(--size-meta);
  color: var(--text-muted-bright);
  text-transform: uppercase;
  letter-spacing: 0.06em;
  margin-bottom: 11px;
}
.readout-main {
  display: flex;
  align-items: baseline;
  gap: 7px;
}
.big {
  font-size: 20px;
  font-weight: 600;
  letter-spacing: -0.02em;
}
.success {
  color: var(--success);
}
.accent-color {
  color: var(--accent);
}
.warning-color {
  color: var(--warning);
}
.uncertain-color {
  color: var(--uncertain);
}
.readout-unit {
  font-size: 12px;
  color: var(--text-secondary);
}
.readout-sub {
  font-size: var(--size-meta);
  color: var(--text-muted);
  margin-top: 3px;
}
.readout-rows {
  display: flex;
  flex-direction: column;
  gap: 5px;
  margin-top: 11px;
}
.readout-row {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
  color: var(--text-secondary);
}
.genres {
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid #161b26;
}
.genre-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.genre-chip {
  font-size: 12px;
  color: var(--text-secondary-bright);
  background: var(--surface-raised);
  border: 1px solid var(--border-subtle-2);
  border-radius: 7px;
  padding: 4px 10px;
}
.genre-chip .mono {
  color: var(--text-muted-bright);
  font-size: var(--size-meta);
}
.columns {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(0, 1fr);
  gap: 18px;
}
.feed-empty {
  color: var(--text-muted);
  font-size: 13px;
  padding: 10px 0;
}
.feed-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px solid #161b26;
}
.feed-row:last-child {
  border-bottom: none;
}
.feed-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
  background: var(--success);
}
.feed-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  color: #dde3ec;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.conn-row {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 10px 0;
}
.conn-icon {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background: var(--success-tint);
  display: grid;
  place-content: center;
  color: var(--success);
}
.conn-text {
  flex: 1;
}
.conn-name {
  font-size: 13px;
  font-weight: 500;
}
.conn-state {
  font-size: var(--size-meta);
  font-weight: 600;
  color: var(--text-muted-bright);
}
.conn-state[data-ok='true'] {
  color: var(--success);
}
.conn-action {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  padding: 4px 10px;
  border-radius: 7px;
  font-size: var(--size-meta);
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.unconfigured {
  text-align: center;
}
.unconfigured p {
  color: var(--text-secondary);
  margin: 8px 0 16px;
}
</style>
