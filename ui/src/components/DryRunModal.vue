<script setup lang="ts">
// DryRunModal (SPEC-DESIGN §6/§8, B10): Smart Fixes preview — before→after
// rows, protected opt-in named and NON-remembered (re-sent on execute too).
// Stale fingerprint (409) -> "Relancer l'aperçu" banner. CTA label carries
// the EXACT payload count. RB-guarded. Execute replays the confirmed payload.
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, api } from '../api/client'
import GuardedButton from './GuardedButton.vue'
import ModalShell from './ModalShell.vue'

const { t } = useI18n()
const emit = defineEmits<{ close: []; executed: [] }>()

interface PayloadEntry {
  content_id: string
  field: string
  before: string | null
  after: string | null
}
interface DryRun {
  payload: PayloadEntry[]
  skipped_protected: Array<{ content_id: string; name: string }>
  fingerprint: unknown
}

const dry = ref<DryRun | null>(null)
const loading = ref(true)
const stale = ref(false)
const submitting = ref(false)
const includeProtected = ref<string[]>([])

async function runDryRun() {
  loading.value = true
  stale.value = false
  dry.value = await api.post<DryRun>('/api/smartfixes/dry-run', {
    include_protected_ids: includeProtected.value,
  })
  loading.value = false
}

onMounted(runDryRun)

function toggleProtected(id: string) {
  includeProtected.value = includeProtected.value.includes(id)
    ? includeProtected.value.filter((x) => x !== id)
    : [...includeProtected.value, id]
  void runDryRun() // re-plan: the opt-in changes what the payload contains
}

async function execute() {
  if (!dry.value) return
  submitting.value = true
  try {
    await api.post('/api/smartfixes/execute', {
      payload: dry.value.payload,
      fingerprint: dry.value.fingerprint,
      include_protected_ids: includeProtected.value,
    })
    emit('executed')
    emit('close')
  } catch (err) {
    if (err instanceof ApiError && err.code === 'stale_snapshot') stale.value = true
  } finally {
    submitting.value = false
  }
}

const count = computed(() => dry.value?.payload.length ?? 0)
</script>

<template>
  <ModalShell width="560px" @close="emit('close')">
    <div class="body">
      <h3>{{ t('smartfixes.dryrun.title') }}</h3>
      <p class="lede">{{ t('smartfixes.dryrun.lede') }}</p>

      <div v-if="stale" class="stale-banner">{{ t('smartfixes.dryrun.stale') }}</div>

      <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
      <template v-else-if="dry">
        <div v-if="dry.payload.length" class="changes">
          <div v-for="(entry, i) in dry.payload" :key="i" class="change">
            <span class="field mono">{{ entry.field }}</span>
            <span class="before">{{ entry.before || '∅' }}</span>
            <span class="arrow">→</span>
            <span class="after">{{ entry.after }}</span>
          </div>
        </div>
        <p v-else class="no-changes">{{ t('smartfixes.dryrun.noChanges') }}</p>

        <div v-if="dry.skipped_protected.length" class="protected">
          <div class="protected-label">🔒 {{ t('smartfixes.dryrun.protectedLabel') }}</div>
          <label
            v-for="entry in dry.skipped_protected"
            :key="entry.content_id"
            class="protected-row"
          >
            <input
              type="checkbox"
              :checked="includeProtected.includes(entry.content_id)"
              @change="toggleProtected(entry.content_id)"
            />
            <span>{{ entry.name }}</span>
          </label>
        </div>
      </template>

      <div class="actions">
        <button class="btn-ghost" @click="emit('close')">{{ t('common.cancel') }}</button>
        <button v-if="stale" class="btn-accent" @click="runDryRun">
          {{ t('smartfixes.dryrun.rerun') }}
        </button>
        <GuardedButton
          v-else
          :label="t('smartfixes.dryrun.confirm', { n: count })"
          tone="primary"
          :disabled="submitting || count === 0"
          @click="execute"
        />
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
.stale-banner {
  background: var(--warning-tint);
  border: 1px solid var(--warning-border);
  color: var(--warning-text);
  border-radius: 9px;
  padding: 10px 13px;
  margin-top: 13px;
  font-size: 12.5px;
}
.loading {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin-top: 14px;
}
.changes {
  margin-top: 14px;
  max-height: 280px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.change {
  display: flex;
  align-items: center;
  gap: 9px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 11px;
  font-size: 12.5px;
}
.field {
  font-size: 11px;
  color: var(--text-muted);
  min-width: 56px;
}
.before {
  color: var(--text-muted-bright);
  text-decoration: line-through;
}
.arrow {
  color: var(--accent);
}
.after {
  color: var(--text-secondary-bright);
  flex: 1;
}
.no-changes {
  color: var(--text-muted-bright);
  font-size: 13px;
  margin-top: 14px;
}
.protected {
  margin-top: 14px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 12px;
}
.protected-label {
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 8px;
}
.protected-row {
  display: flex;
  align-items: center;
  gap: 9px;
  padding: 5px 0;
  font-size: 12.5px;
  color: var(--text-secondary-bright);
  cursor: pointer;
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
.btn-accent {
  background: var(--accent);
  border: none;
  color: #06131f;
  padding: 9px 18px;
  border-radius: 9px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
}
</style>
