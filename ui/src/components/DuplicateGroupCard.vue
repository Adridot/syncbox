<script setup lang="ts">
// Duplicate group (SPEC-DESIGN §6, SPEC-UNIFIED §5.4): side-by-side member
// comparison with the justifying attributes, an EXPLAINED suggested keeper
// (D6 reason), a re-selectable keeper radio, per-group confirmation (D5 —
// no auto bulk), explicit outcome text (B10) and a dismiss.
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'

import type { DuplicateGroup } from '../api/types'
import QualityBadge from './QualityBadge.vue'
import { useJobsStore } from '../stores/jobs'
import { useStatusStore } from '../stores/status'

const props = defineProps<{ group: DuplicateGroup; index: number }>()
const emit = defineEmits<{
  resolve: [keeper: string, losers: string[]]
  dismiss: []
}>()
const { t } = useI18n()
const status = useStatusStore()
const jobs = useJobsStore()

const keeperId = ref(props.group.keeper.content_id)
const losers = computed(() =>
  props.group.members
    .filter((member) => member.content_id !== keeperId.value)
    .map((member) => member.content_id),
)

const confTone = computed(() =>
  props.group.confidence >= 95 ? 'success' : props.group.confidence >= 80 ? 'accent' : 'warning',
)
</script>

<template>
  <div class="group">
    <div class="group-head">
      <span class="gnum mono">{{ t('duplicates.group', { n: index + 1 }) }}</span>
      <span class="method" :data-method="group.method">{{
        t(`duplicates.method.${group.method}`, group.method)
      }}</span>
      <span class="reason">{{ t(`duplicates.reason.${group.keeper.reason}`) }}</span>
      <span class="spacer" />
      <span class="conf mono" :data-tone="confTone">conf {{ group.confidence }}</span>
      <span v-if="group.warning" class="warn-chip">⚠ {{ t('duplicates.titlesDiverge') }}</span>
    </div>

    <div class="members">
      <label
        v-for="member in group.members"
        :key="member.content_id"
        class="member"
        :data-keeper="member.content_id === keeperId"
      >
        <div class="member-top">
          <input
            v-model="keeperId"
            type="radio"
            :name="`keeper-${group.key}`"
            :value="member.content_id"
          />
          <span class="tag" :data-keeper="member.content_id === keeperId">{{
            member.content_id === keeperId ? t('duplicates.keepTag') : t('duplicates.removeTag')
          }}</span>
          <span class="spacer" />
          <QualityBadge :verdict="member.quality_verdict" />
        </div>
        <div class="member-title">{{ member.title }}</div>
        <div class="member-artist">{{ member.artist }}</div>
        <div class="attrs">
          <div class="attr">
            <span>{{ t('duplicates.attrQuality') }}</span>
            <span class="mono">{{ member.bit_rate ? `${member.bit_rate} kbps` : '—' }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.attrFile') }}</span>
            <span class="mono" :data-missing="member.file_missing">{{
              member.file_missing ? t('duplicates.fileMissing') : t('duplicates.filePresent')
            }}</span>
          </div>
          <div class="attr">
            <span>{{ t('ownership.label') }}</span>
            <span class="mono" :data-ownership="member.ownership">{{
              t(`ownership.${member.ownership}`)
            }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.attrPlaylists') }}</span>
            <span class="mono">{{ member.playlist_count }}</span>
          </div>
          <div class="attr">
            <span>{{ t('duplicates.attrCues') }}</span>
            <span class="mono">{{ member.cue_count }}</span>
          </div>
        </div>
        <div v-if="member.quality_verdict !== 'ok'" class="quality-line">
          {{ t(`duplicates.qualityReason.${member.quality_reason}`, member.quality_reason) }}
        </div>
      </label>
    </div>

    <div class="group-foot">
      <span class="outcome">{{
        t('duplicates.outcome', {
          keep: group.members.find((m) => m.content_id === keeperId)?.title ?? keeperId,
          n: losers.length,
        })
      }}</span>
      <span class="spacer" />
      <button class="dismiss" @click="emit('dismiss')">{{ t('duplicates.notADuplicate') }}</button>
      <button
        class="resolve"
        :disabled="status.rbOpen || jobs.jobRunning || !losers.length"
        @click="emit('resolve', keeperId, losers)"
      >
        {{ status.rbOpen ? t('rbGuard.blocked') : t('duplicates.resolveGroup') }}
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
  flex-wrap: wrap;
}
.gnum {
  font-size: var(--size-meta);
  font-weight: 700;
  color: var(--text-muted-bright);
  background: #161b26;
  border-radius: 6px;
  padding: 3px 8px;
  text-transform: uppercase;
}
.method {
  font-size: var(--size-meta);
  font-weight: 600;
  border-radius: 6px;
  padding: 2px 8px;
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
}
.method[data-method='fuzzy'] {
  background: var(--uncertain-tint);
  border-color: var(--uncertain-border);
  color: var(--uncertain);
}
.reason {
  font-size: 12.5px;
  color: var(--text-secondary);
}
.spacer {
  flex: 1;
}
.conf {
  font-size: 12px;
}
.conf[data-tone='success'] {
  color: var(--success);
}
.conf[data-tone='accent'] {
  color: var(--accent);
}
.conf[data-tone='warning'] {
  color: var(--warning);
}
.warn-chip {
  font-size: var(--size-meta);
  color: var(--warning);
  font-weight: 600;
}
.members {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
  gap: 12px;
  padding: 14px 16px;
}
.member {
  border: 1px solid var(--border-2);
  border-radius: var(--radius-inner);
  padding: 13px;
  cursor: pointer;
  display: block;
}
.member:hover {
  border-color: #2a3242;
}
.member[data-keeper='true'] {
  border-color: rgba(52, 211, 153, 0.4);
  background: rgba(52, 211, 153, 0.04);
}
.member-top {
  display: flex;
  align-items: center;
  gap: 9px;
  margin-bottom: 11px;
}
.member-top input {
  accent-color: var(--success);
}
.tag {
  font-size: var(--size-label);
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  border-radius: 5px;
  padding: 2px 7px;
  color: var(--text-muted-bright);
  background: var(--neutral-tint);
}
.tag[data-keeper='true'] {
  color: #5fe0b0;
  background: var(--success-tint);
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
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px 12px;
  font-size: 11.5px;
}
.attr {
  display: flex;
  justify-content: space-between;
  gap: 8px;
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
.mono {
  font-family: var(--font-mono);
}
.quality-line {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #161b26;
  font-size: 11.5px;
  color: var(--uncertain);
  line-height: 1.4;
}
.group-foot {
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
  min-width: 0;
}
.dismiss {
  background: transparent;
  border: 1px solid #2a3140;
  color: var(--text-secondary);
  padding: 7px 13px;
  border-radius: 8px;
  font-size: 12.5px;
  cursor: pointer;
  white-space: nowrap;
}
.resolve {
  background: var(--accent-tint);
  border: 1px solid var(--accent-border);
  color: var(--accent-hover);
  padding: 7px 14px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
}
.resolve:disabled {
  opacity: 0.55;
  cursor: default;
}
</style>
