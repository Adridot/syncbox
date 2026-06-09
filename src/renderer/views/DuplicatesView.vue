<script setup lang="ts">
import {
  AlertTriangle,
  Copy,
  HardDriveDownload,
  Loader2,
  Search,
  ShieldCheck,
  Sparkles,
  Trash2,
  X,
} from "@lucide/vue";
import type { DuplicateGroup, DuplicateTrack } from "../lib/api";
import { formatBytes, formatDuration } from "../lib/format";
import { t } from "../i18n";
import { useDuplicates } from "../composables/queries/useDuplicates";
import { useSystemStore } from "../stores/system";

const duplicates = useDuplicates();
const system = useSystemStore();

function qualityLine(track: DuplicateTrack): string {
  const parts: string[] = [];
  if (track.fileType) parts.push(track.fileType);
  if (track.bitRate) parts.push(`${track.bitRate} kbps`);
  if (track.bpm) parts.push(`${track.bpm.toFixed(0)} BPM`);
  parts.push(formatBytes(track.fileSize));
  return parts.join(" · ");
}

async function confirmResolveGroup(group: DuplicateGroup): Promise<void> {
  const keeper = duplicates.keeperOf(group);
  const losers = group.tracks.filter((t) => t.contentId !== keeper);
  const willDeleteFiles =
    Boolean(duplicates.deleteFiles[group.groupId]) &&
    losers.some((t) => !t.protected && !t.fileMissing);
  const lines = [
    t("duplicates.confirm.keep", {
      label: trackLabel(group.tracks.find((tr) => tr.contentId === keeper)),
    }),
    t("duplicates.confirm.removeCopies", { count: losers.length }),
    willDeleteFiles
      ? t("duplicates.confirm.filesDeleted")
      : t("duplicates.confirm.filesKept"),
    t("duplicates.confirm.relink"),
    t("duplicates.confirm.backup"),
  ];
  if (window.confirm(lines.join("\n\n"))) {
    await duplicates.resolveGroup(group);
  }
}

function trackLabel(track: DuplicateTrack | undefined): string {
  if (!track) return "?";
  return `${track.artist} – ${track.title}`;
}

async function confirmResolveAll(): Promise<void> {
  if (window.confirm(t("duplicates.confirm.all", { count: duplicates.isrcGroupCount }))) {
    await duplicates.resolveAllIsrc();
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto px-6 py-6 md:px-8">
    <div class="mx-auto flex max-w-4xl flex-col gap-6">
      <!-- Controls -->
      <section class="rounded-xl border border-outline-variant bg-surface-container p-5">
        <div class="flex flex-wrap items-center gap-4">
          <label class="flex items-center gap-2 text-sm text-on-surface">
            <input v-model="duplicates.useIsrc" type="checkbox" class="accent-primary" />
            {{ $t("duplicates.matchByIsrc") }}
            <span class="text-xs text-on-surface-variant">{{ $t("duplicates.sameRecording") }}</span>
          </label>
          <label class="flex items-center gap-2 text-sm text-on-surface">
            <input v-model="duplicates.useFuzzy" type="checkbox" class="accent-primary" />
            {{ $t("duplicates.fuzzy") }}
          </label>
          <label
            v-if="duplicates.useFuzzy"
            class="flex items-center gap-2 text-xs text-on-surface-variant"
          >
            {{ $t("duplicates.similarity") }}
            <input
              v-model.number="duplicates.fuzzyThreshold"
              type="range"
              min="0.75"
              max="0.98"
              step="0.01"
              class="accent-primary"
            />
            {{ Math.round(duplicates.fuzzyThreshold * 100) }}%
          </label>
          <button
            type="button"
            class="ml-auto inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
            :disabled="duplicates.scanning || !system.api"
            @click="duplicates.scan()"
          >
            <Loader2 v-if="duplicates.scanning" :size="15" class="animate-spin" aria-hidden="true" />
            <Search v-else :size="15" aria-hidden="true" />
            {{ $t("duplicates.scanCollection") }}
          </button>
        </div>
      </section>

      <!-- Summary + bulk action -->
      <div
        v-if="duplicates.scanned && !duplicates.unavailableReason"
        class="flex items-center justify-between"
      >
        <p class="text-sm text-on-surface-variant">
          <strong class="text-on-surface">{{ duplicates.groupCount }}</strong>
          {{ $t("duplicates.groupsSummary") }}
          <strong class="text-on-surface">{{ duplicates.totalTracks }}</strong>
          {{ $t("duplicates.tracksSuffix") }}
        </p>
        <button
          v-if="duplicates.isrcGroupCount > 0"
          type="button"
          class="inline-flex items-center gap-2 rounded border border-secondary px-3 py-1.5 text-xs font-semibold text-secondary hover:bg-secondary/10 disabled:opacity-60"
          :disabled="duplicates.scanning"
          @click="confirmResolveAll"
        >
          <Sparkles :size="14" aria-hidden="true" />
          {{ $t("duplicates.autoResolve", { count: duplicates.isrcGroupCount }) }}
        </button>
      </div>

      <p
        v-if="duplicates.unavailableReason"
        class="rounded-xl border border-error/40 bg-error/5 px-5 py-4 text-sm text-error"
      >
        {{ duplicates.unavailableReason }}
      </p>

      <p
        v-else-if="duplicates.scanned && duplicates.groupCount === 0"
        class="rounded-xl border border-outline-variant bg-surface-container px-5 py-8 text-center text-sm text-on-surface-variant"
      >
        {{ $t("duplicates.noDuplicates") }}
      </p>

      <p
        v-else-if="!duplicates.scanned"
        class="rounded-xl border border-dashed border-outline-variant px-5 py-10 text-center text-sm text-on-surface-variant"
      >
        {{ $t("duplicates.scanHint") }}
      </p>

      <!-- Groups -->
      <section
        v-for="group in duplicates.groups"
        :key="group.groupId"
        class="rounded-xl border border-outline-variant bg-surface-container"
      >
        <header
          class="flex items-center gap-2 border-b border-outline-variant px-5 py-3"
        >
          <Copy :size="16" class="text-on-surface-variant" aria-hidden="true" />
          <span
            class="rounded-full px-2 py-0.5 text-xs font-semibold"
            :class="
              group.reason === 'isrc'
                ? 'bg-secondary/15 text-secondary'
                : 'bg-tertiary/15 text-tertiary'
            "
          >
            {{ group.reason === "isrc" ? $t("duplicates.sameIsrc") : $t("duplicates.similarMetadata") }}
            · {{ group.confidence }}%
          </span>
          <span class="text-xs text-on-surface-variant">{{ $t("duplicates.copies", { count: group.tracks.length }) }}</span>

          <div class="ml-auto flex items-center gap-2">
            <label
              class="flex items-center gap-1.5 text-xs text-on-surface-variant"
              :title="$t('duplicates.deleteFilesTitle')"
            >
              <input
                v-model="duplicates.deleteFiles[group.groupId]"
                type="checkbox"
                class="accent-error"
              />
              <HardDriveDownload :size="13" aria-hidden="true" />
              {{ $t("duplicates.deleteFiles") }}
            </label>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded border border-outline px-2.5 py-1 text-xs text-on-surface-variant hover:border-on-surface hover:text-on-surface disabled:opacity-60"
              :disabled="duplicates.resolvingGroupId === group.groupId"
              @click="duplicates.dismissGroup(group)"
            >
              <X :size="13" aria-hidden="true" />
              {{ $t("duplicates.notDuplicate") }}
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded bg-primary px-3 py-1 text-xs font-bold text-white disabled:opacity-60"
              :disabled="duplicates.resolvingGroupId === group.groupId"
              @click="confirmResolveGroup(group)"
            >
              <Loader2
                v-if="duplicates.resolvingGroupId === group.groupId"
                :size="13"
                class="animate-spin"
                aria-hidden="true"
              />
              <Trash2 v-else :size="13" aria-hidden="true" />
              {{ $t("duplicates.keepSelected") }}
            </button>
          </div>
        </header>

        <p
          v-if="group.note"
          class="flex items-start gap-2 border-b border-tertiary/30 bg-tertiary/5 px-5 py-2 text-xs text-tertiary"
        >
          <AlertTriangle :size="14" class="mt-0.5 shrink-0" aria-hidden="true" />
          {{ group.note }}
        </p>

        <ul>
          <li
            v-for="track in group.tracks"
            :key="track.contentId"
            class="flex items-start gap-3 border-b border-outline-variant px-5 py-3 last:border-b-0"
            :class="
              duplicates.keeperOf(group) === track.contentId
                ? 'bg-secondary/5'
                : ''
            "
          >
            <input
              type="radio"
              class="mt-1 accent-secondary"
              :name="`keeper-${group.groupId}`"
              :checked="duplicates.keeperOf(group) === track.contentId"
              @change="duplicates.setKeeper(group, track.contentId)"
            />
            <div class="min-w-0 flex-1">
              <div class="flex items-center gap-2">
                <strong class="truncate text-sm text-on-surface">{{ track.title }}</strong>
                <span
                  v-if="duplicates.keeperOf(group) === track.contentId"
                  class="rounded-full bg-secondary/15 px-2 py-0.5 text-[10px] font-bold uppercase text-secondary"
                >
                  {{ $t("duplicates.keep") }}
                </span>
              </div>
              <p class="truncate text-xs text-on-surface-variant">{{ track.artist }}</p>
              <div class="mt-1 flex flex-wrap items-center gap-1.5">
                <span class="text-[11px] text-on-surface-variant">
                  {{ formatDuration(track.durationMs) }} · {{ qualityLine(track) }}
                </span>
                <span
                  v-if="track.protected"
                  class="inline-flex items-center gap-0.5 rounded bg-secondary/15 px-1.5 py-0.5 text-[10px] font-semibold text-secondary"
                >
                  <ShieldCheck :size="11" aria-hidden="true" /> {{ $t("duplicates.permanent") }}
                </span>
                <span
                  v-if="track.cueCount"
                  class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
                >
                  {{ $t("duplicates.cues", { count: track.cueCount }) }}
                </span>
                <span
                  v-if="track.playlistCount"
                  class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
                >
                  {{ $t("duplicates.playlists", { count: track.playlistCount }) }}
                </span>
                <span
                  v-if="track.tagCount"
                  class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
                >
                  {{ $t("duplicates.tags", { count: track.tagCount }) }}
                </span>
                <span
                  v-if="track.fileMissing"
                  class="rounded bg-error/15 px-1.5 py-0.5 text-[10px] font-semibold text-error"
                >
                  {{ $t("duplicates.fileMissing") }}
                </span>
              </div>
              <p
                v-if="track.filePath"
                class="mt-0.5 truncate text-[10px] text-on-surface-variant/70"
                :title="track.filePath"
              >
                {{ track.filePath }}
              </p>
            </div>
          </li>
        </ul>
      </section>
    </div>
  </div>
</template>
