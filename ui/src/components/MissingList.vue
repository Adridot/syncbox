<script setup lang="ts">
// Shared missing-entries list (SPEC-DESIGN §2/§6). Rows: PurchaseLinks
// (legal path first; absent for removed_from_source — server filters, UI
// must not re-add), manual relink (collection scope only), and remove (G3
// soft-delete, RB-guarded). Used by the health hub tab and the Missing
// center. Status transitions (§5.5) + restore (D22) for app-DB scopes.
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { api } from '../api/client'
import ManualRelinkModal from './ManualRelinkModal.vue'
import ModalShell from './ModalShell.vue'
import PurchaseLinks from './PurchaseLinks.vue'
import ScopeBadge from './ScopeBadge.vue'
import StatusBadge from './StatusBadge.vue'
import type { MissingEntry } from '../stores/missing'

const { t } = useI18n()
defineProps<{ entries: MissingEntry[]; showScope?: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const relinkTarget = ref<MissingEntry | null>(null)

async function remove(entry: MissingEntry) {
  if (!entry.content_id) return
  // G3: soft-delete via _mutate (423-guarded, reversible, no audio delete).
  await api.post(`/api/missing/collection/${entry.content_id}/remove`)
  emit('changed')
}

async function restore(entry: MissingEntry) {
  // D22 restore is only meaningful for app-DB scopes (library/event).
  await api.post(`/api/missing/${entry.scope}/${entry.id}/restore`)
  emit('changed')
}
</script>

<template>
  <div class="list">
    <div v-for="entry in entries" :key="`${entry.scope}-${entry.id}`" class="mrow">
      <div class="mtext">
        <div class="mtitle">
          {{ entry.title }}
          <span class="martist">— {{ entry.artist }}</span>
        </div>
        <div class="mmeta">
          <ScopeBadge v-if="showScope" :scope="entry.scope" />
          <StatusBadge :status="entry.status" />
          <span v-if="entry.file_path" class="mpath mono">{{ entry.file_path }}</span>
        </div>
      </div>
      <div class="mactions">
        <!-- legal path first; server already excludes removed_from_source -->
        <PurchaseLinks v-if="entry.purchase_links.length" :links="entry.purchase_links" />
        <button
          v-if="entry.scope === 'collection' && entry.content_id"
          class="row-btn accent"
          @click="relinkTarget = entry"
        >
          {{ t('missing.actions.relink') }}
        </button>
        <button
          v-if="entry.scope === 'collection' && entry.content_id"
          class="row-btn danger"
          @click="remove(entry)"
        >
          {{ t('missing.actions.remove') }}
        </button>
        <button
          v-if="entry.scope !== 'collection'"
          class="row-btn"
          @click="restore(entry)"
        >
          {{ t('missing.actions.restore') }}
        </button>
      </div>
    </div>
    <div v-if="!entries.length" class="empty">{{ t('missing.empty') }}</div>

    <ModalShell v-if="relinkTarget" width="540px" @close="relinkTarget = null">
      <div class="modal-pad">
        <ManualRelinkModal
          :content-id="relinkTarget.content_id!"
          :title="relinkTarget.title"
          :candidates="relinkTarget.relink_candidates"
          @close="relinkTarget = null"
          @relinked="emit('changed')"
        />
      </div>
    </ModalShell>
  </div>
</template>

<style scoped>
.list {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 13px;
  overflow: clip;
}
.mrow {
  display: flex;
  align-items: center;
  gap: 14px;
  padding: 13px 18px;
  border-bottom: 1px solid var(--border-subtle);
}
.mrow:last-child {
  border-bottom: none;
}
.mtext {
  flex: 1;
  min-width: 0;
}
.mtitle {
  font-size: 13.5px;
  font-weight: 500;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.martist {
  color: var(--text-muted-bright);
  font-weight: 400;
}
.mmeta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 4px;
}
.mpath {
  font-size: 11.5px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.mono {
  font-family: var(--font-mono);
}
.mactions {
  display: flex;
  align-items: center;
  gap: 7px;
  flex: none;
}
.row-btn {
  background: transparent;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 6px 12px;
  border-radius: 7px;
  font-size: 12px;
  cursor: pointer;
}
.row-btn.accent {
  background: var(--accent-tint);
  border-color: var(--accent-border);
  color: var(--accent-hover);
  font-weight: 600;
}
.row-btn.danger {
  color: var(--danger-text);
}
.empty {
  padding: 42px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
}
.modal-pad {
  padding: 22px;
}
</style>
