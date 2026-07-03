<script setup lang="ts">
// DuplicateGroupCard (SPEC-DESIGN §6/§8): side-by-side comparison, keeper
// re-selectable (radio) with the explicit reason, per-group confirm (no bulk
// auto). Warning groups (divergent titles) are excluded from bulk. Resolve
// runs the 428 permanent-delete consent loop via the global broker; a re-
// entrant retry is safe (the sidecar skips committed DB work).
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError } from '../api/client'
import { useDuplicatesStore, type DuplicateGroup } from '../stores/duplicates'
import QualityBadge from './QualityBadge.vue'

const { t } = useI18n()
const props = defineProps<{ group: DuplicateGroup; index: number }>()
const emit = defineEmits<{ stale: [] }>()
const duplicates = useDuplicatesStore()

const keeper = ref(props.group.keeper.content_id)
const resolving = ref(false)

async function resolve() {
  resolving.value = true
  try {
    const losers = props.group.members
      .map((m) => m.content_id)
      .filter((id) => id !== keeper.value)
    await duplicates.resolve(keeper.value, losers)
  } catch (err) {
    // 409 stale_snapshot -> the scan is stale, re-run it (bubble up)
    if (err instanceof ApiError && err.code === 'stale_snapshot') emit('stale')
  } finally {
    resolving.value = false
  }
}

function fileText(m: DuplicateGroup['members'][number]): string {
  return m.file_missing ? t('duplicates.missing') : t('duplicates.present')
}
</script>

<template>
  <div class="group">
    <div class="group-head">
      <span class="gnum mono">{{ t('duplicates.group') }} {{ index + 1 }}</span>
      <span class="method">{{ group.method }}</span>
      <span class="reason">{{ t('duplicates.keeperReason', { reason: group.keeper.reason }) }}</span>
      <span class="spacer" />
      <span class="mono conf">{{ t('duplicates.conf') }} {{ group.confidence }}</span>
      <span v-if="group.warning" class="warn">⚠ {{ t('duplicates.excludedBulk') }}</span>
    </div>

    <div class="members">
      <label
        v-for="member in group.members"
        :key="member.content_id"
        class="member"
        :data-keeper="keeper === member.content_id"
      >
        <div class="member-top">
          <input v-model="keeper" type="radio" :value="member.content_id" />
          <span class="keeper-tag" :data-on="keeper === member.content_id">{{
            keeper === member.content_id ? t('duplicates.keeper') : t('duplicates.copy')
          }}</span>
          <span class="spacer" />
          <QualityBadge :verdict="member.quality_verdict" />
        </div>
        <div class="member-title">{{ member.title }}</div>
        <div class="member-artist">{{ member.artist }}</div>
        <div class="attrs">
          <div class="attr">
            <span>{{ t('duplicates.quality') }}</span
            ><span class="mono">{{ member.bit_rate ? `${member.bit_rate}k` : '—' }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.file') }}</span
            ><span class="mono" :data-missing="member.file_missing">{{ fileText(member) }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.playlists') }}</span
            ><span class="mono">{{ member.playlist_count }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.cues') }}</span><span class="mono">{{ member.cue_count }}</span>
          </div>
        </div>
      </label>
    </div>

    <div class="footer">
      <span class="outcome">{{
        t('duplicates.outcome', {
          keeper: 1,
          losers: group.members.length - 1,
        })
      }}</span>
      <span class="spacer" />
      <button class="btn-ghost" @click="duplicates.dismiss(group.key)">
        {{ t('duplicates.notDuplicate') }}
      </button>
      <button class="btn-accent" :disabled="resolving" @click="resolve">
        {{ t('duplicates.resolve') }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.group {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-card);
  overflow: clip;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 13px 16px;
  background: var(--surface-2);
  border-bottom: 1px solid var(--border-subtle-2);
}
.gnum {
  font-size: 11px;
  font-weight: 700;
  color: var(--text-muted-bright);
  background: #161b26;
  border-radius: 6px;
  padding: 3px 8px;
}
.method {
  font-size: 12px;
  color: var(--accent-hover);
  font-family: var(--font-mono);
}
.reason {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.spacer {
  flex: 1;
}
.mono {
  font-family: var(--font-mono);
}
.conf {
  font-size: 12px;
  color: var(--text-muted-bright);
}
.warn {
  font-size: 11px;
  color: var(--warning);
  font-weight: 600;
}
.members {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 12px;
  padding: 14px 16px;
}
.member {
  border: 1px solid var(--border);
  border-radius: var(--radius-inner);
  padding: 13px;
  cursor: pointer;
}
.member[data-keeper='true'] {
  border-color: var(--success-border);
  background: var(--success-tint);
}
.member-top {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 11px;
}
.keeper-tag {
  font-size: 10.5px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  font-weight: 700;
  color: var(--text-muted);
}
.keeper-tag[data-on='true'] {
  color: #5fe0b0;
}
.member-title {
  font-size: 13.5px;
  font-weight: 600;
  line-height: 1.3;
}
.member-artist {
  font-size: 12px;
  color: var(--text-muted-bright);
  margin-bottom: 11px;
}
.attrs {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 7px 12px;
  font-size: 11.5px;
}
.attr {
  display: flex;
  justify-content: space-between;
}
.attr span:first-child {
  color: var(--text-muted);
}
.attr .mono {
  color: var(--text-secondary-bright);
}
.attr .mono[data-missing='true'] {
  color: var(--danger-text);
}
.footer {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--surface-2);
  border-top: 1px solid var(--border-subtle-2);
}
.outcome {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.btn-ghost {
  background: transparent;
  border: 1px solid var(--border-2);
  color: var(--text-secondary);
  padding: 7px 13px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
}
.btn-accent {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.btn-accent:disabled {
  opacity: 0.5;
  cursor: default;
}
</style>
