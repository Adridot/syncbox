<script setup lang="ts">
import {
  AlertTriangle,
  CheckCircle2,
  Copy,
  Loader2,
  RefreshCw,
  Search,
  ShieldCheck,
  Sparkles,
  Tag,
  Trash2,
} from "@lucide/vue";
import { ref } from "vue";
import type { UntaggedSuggestion } from "../lib/api";
import { formatDuration } from "../lib/format";
import { t } from "../i18n";
import { useUntagged } from "../composables/queries/useUntagged";
import { useSystemStore } from "../stores/system";

const untagged = useUntagged();
const system = useSystemStore();

const tagInput = ref("");

// Visual presentation stays here; the label/hint text is resolved through i18n
// (untagged.suggestion.<key> / <key>Hint) at render time.
type Meta = { cls: string; icon: unknown; key: string };
const suggestionMeta: Record<UntaggedSuggestion, Meta> = {
  junk: { cls: "bg-error/15 text-error", icon: AlertTriangle, key: "junk" },
  dup_of_tagged: { cls: "bg-tertiary/15 text-tertiary", icon: Tag, key: "dupOfTagged" },
  alt_version: { cls: "bg-secondary/15 text-secondary", icon: Copy, key: "altVersion" },
  review: { cls: "bg-primary/15 text-primary", icon: Sparkles, key: "review" },
};

const filterChips: Array<{ key: UntaggedSuggestion | "all"; labelKey: string }> = [
  { key: "all", labelKey: "all" },
  { key: "review", labelKey: "review" },
  { key: "junk", labelKey: "junk" },
  { key: "dup_of_tagged", labelKey: "dupOfTagged" },
  { key: "alt_version", labelKey: "altVersion" },
];

async function applyTag(): Promise<void> {
  const name = tagInput.value.trim();
  if (!name) return;
  await untagged.applyTag(name);
  tagInput.value = "";
}

async function confirmDelete(): Promise<void> {
  const n = untagged.selectedIds.size;
  if (n === 0) return;
  if (window.confirm(t("untagged.confirmDelete", { count: n }))) {
    await untagged.deleteSelected();
  }
}
</script>

<template>
  <div class="flex h-full flex-col overflow-hidden">
    <!-- Header / controls -->
    <div class="shrink-0 border-b border-outline-variant bg-surface-container px-6 py-4">
      <div class="flex flex-wrap items-center gap-3">
        <div class="flex items-center gap-2 text-sm text-on-surface-variant">
          <Tag :size="18" aria-hidden="true" />
          {{ $t("untagged.intro") }}
        </div>
        <button
          type="button"
          class="ml-auto inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-1.5 text-sm font-semibold text-on-surface hover:border-primary disabled:opacity-60"
          :disabled="untagged.loading || !system.api"
          @click="untagged.load()"
        >
          <Loader2 v-if="untagged.loading" :size="15" class="animate-spin" aria-hidden="true" />
          <RefreshCw v-else :size="15" aria-hidden="true" />
          {{ $t("untagged.refresh") }}
        </button>
      </div>

      <div
        v-if="untagged.scanned && !untagged.unavailableReason"
        class="mt-3 flex flex-wrap items-center gap-2"
      >
        <span class="text-sm text-on-surface-variant">
          <strong class="text-on-surface">{{ untagged.untaggedCount }}</strong> {{ $t("untagged.untaggedOf") }}
          <strong class="text-on-surface">{{ untagged.total }}</strong> {{ $t("untagged.tracksSuffix") }}
        </span>
        <span class="mx-1 h-4 w-px bg-outline-variant" aria-hidden="true" />
        <button
          v-for="chip in filterChips"
          :key="chip.key"
          type="button"
          class="rounded-full px-3 py-1 text-xs font-semibold transition-colors"
          :class="
            untagged.suggestionFilter === chip.key
              ? 'bg-primary text-white'
              : 'bg-surface text-on-surface-variant hover:text-on-surface'
          "
          @click="untagged.suggestionFilter = chip.key"
        >
          {{ $t(`untagged.filter.${chip.labelKey}`) }}
          <template v-if="chip.key !== 'all'"> ({{ untagged.counts[chip.key] ?? 0 }})</template>
        </button>

        <div class="relative ml-auto">
          <Search
            :size="14"
            class="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-on-surface-variant"
            aria-hidden="true"
          />
          <input
            v-model="untagged.search"
            type="search"
            :placeholder="$t('untagged.searchPlaceholder')"
            class="w-56 rounded border border-outline bg-surface-container-high px-3 py-1.5 pl-8 text-sm text-on-surface focus:border-primary focus:outline-none"
          />
        </div>
      </div>
    </div>

    <!-- States -->
    <div
      v-if="untagged.unavailableReason"
      class="m-6 rounded-xl border border-error/40 bg-error/5 px-5 py-4 text-sm text-error"
    >
      {{ untagged.unavailableReason }}
    </div>

    <div
      v-else-if="untagged.loading && !untagged.scanned"
      class="grid flex-1 place-items-center text-sm text-on-surface-variant"
    >
      <span class="inline-flex items-center gap-2">
        <Loader2 :size="16" class="animate-spin" aria-hidden="true" /> {{ $t("untagged.readingCollection") }}
      </span>
    </div>

    <div
      v-else-if="untagged.scanned && untagged.untaggedCount === 0"
      class="grid flex-1 place-items-center p-8 text-center"
    >
      <div class="max-w-sm">
        <div class="mx-auto mb-4 grid h-14 w-14 place-items-center rounded-full bg-secondary/15">
          <CheckCircle2 class="text-secondary" :size="26" aria-hidden="true" />
        </div>
        <h3 class="mb-1 text-lg font-bold text-on-surface">{{ $t("untagged.everythingTagged") }}</h3>
        <p class="text-sm text-on-surface-variant">
          {{ $t("untagged.everythingTaggedHint") }}
        </p>
      </div>
    </div>

    <!-- Table -->
    <div v-else class="min-h-0 flex-1 overflow-y-auto">
      <table class="w-full border-collapse text-sm">
        <thead
          class="sticky top-0 z-10 bg-surface-container text-left text-xs uppercase tracking-wide text-on-surface-variant"
        >
          <tr class="border-b border-outline-variant">
            <th class="w-10 px-4 py-2">
              <input
                type="checkbox"
                class="h-4 w-4 accent-primary"
                :checked="untagged.allFilteredSelected"
                @change="untagged.toggleAllFiltered(($event.target as HTMLInputElement).checked)"
              />
            </th>
            <th class="px-3 py-2 font-semibold">{{ $t("untagged.colTrack") }}</th>
            <th class="px-3 py-2 font-semibold">{{ $t("untagged.colWhy") }}</th>
            <th class="px-3 py-2 font-semibold">{{ $t("untagged.colInfo") }}</th>
            <th class="px-3 py-2 text-right font-semibold">{{ $t("untagged.colLength") }}</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="track in untagged.filteredTracks"
            :key="track.contentId"
            class="border-b border-outline-variant/60 transition-colors hover:bg-surface-container-high/50"
            :class="untagged.isSelected(track.contentId) ? 'bg-primary/5' : ''"
          >
            <td class="px-4 py-2 align-top">
              <input
                type="checkbox"
                class="mt-0.5 h-4 w-4 accent-primary"
                :checked="untagged.isSelected(track.contentId)"
                @change="untagged.toggle(track.contentId, ($event.target as HTMLInputElement).checked)"
              />
            </td>
            <td class="px-3 py-2 align-top">
              <div class="min-w-0">
                <div class="truncate font-semibold text-on-surface">
                  {{ track.title || $t("untagged.noTitle") }}
                </div>
                <div class="truncate text-xs text-on-surface-variant">{{ track.artist || "—" }}</div>
              </div>
            </td>
            <td class="px-3 py-2 align-top">
              <span
                class="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold"
                :class="suggestionMeta[track.suggestion].cls"
                :title="$t(`untagged.suggestion.${suggestionMeta[track.suggestion].key}Hint`)"
              >
                <component :is="suggestionMeta[track.suggestion].icon" :size="12" aria-hidden="true" />
                {{ $t(`untagged.suggestion.${suggestionMeta[track.suggestion].key}`) }}
              </span>
              <span
                v-if="track.suggestionDetail"
                class="mt-0.5 block truncate text-[10px] text-on-surface-variant"
                :title="track.suggestionDetail"
              >
                → {{ track.suggestionDetail }}
              </span>
            </td>
            <td class="px-3 py-2 align-top">
              <div class="flex flex-wrap items-center gap-1">
                <span
                  v-if="track.protected"
                  class="inline-flex items-center gap-0.5 rounded bg-secondary/15 px-1.5 py-0.5 text-[10px] font-semibold text-secondary"
                  :title="$t('untagged.permanentTitle')"
                >
                  <ShieldCheck :size="11" aria-hidden="true" /> {{ $t("untagged.permanent") }}
                </span>
                <span
                  v-if="track.playlistCount"
                  class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
                >
                  {{ track.playlistCount }} {{ track.playlistCount > 1 ? $t("untagged.playlists") : $t("untagged.playlist") }}
                </span>
                <span
                  v-if="track.fileMissing"
                  class="rounded bg-error/15 px-1.5 py-0.5 text-[10px] font-semibold text-error"
                >
                  {{ $t("untagged.fileMissing") }}
                </span>
                <span
                  v-if="!track.isrc"
                  class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
                >
                  {{ $t("untagged.noIsrc") }}
                </span>
              </div>
            </td>
            <td class="whitespace-nowrap px-3 py-2 text-right align-top font-mono text-xs text-on-surface-variant">
              {{ formatDuration(track.durationMs) }}
            </td>
          </tr>
          <tr v-if="untagged.filteredTracks.length === 0">
            <td colspan="5" class="px-4 py-10 text-center text-sm text-on-surface-variant">
              {{ $t("untagged.noMatch") }}
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Action bar -->
    <div
      v-if="untagged.selectedIds.size > 0"
      class="shrink-0 border-t border-outline-variant bg-surface-container px-6 py-3"
    >
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
        <span class="inline-flex items-center gap-1.5 rounded bg-primary/15 px-2.5 py-1 text-xs font-bold text-primary">
          {{ $t("untagged.selectedCount", { count: untagged.selectedIds.size }) }}
        </span>
        <button
          type="button"
          class="text-xs font-semibold text-on-surface-variant hover:text-on-surface"
          @click="untagged.clearSelection()"
        >
          {{ $t("untagged.clear") }}
        </button>

        <div class="ml-auto flex flex-wrap items-center gap-2">
          <input
            v-model="tagInput"
            list="untagged-tags"
            :placeholder="$t('untagged.tagToApply')"
            class="w-52 rounded border border-outline bg-surface-container-high px-3 py-1.5 text-sm text-on-surface focus:border-primary focus:outline-none"
            @keydown.enter.prevent="applyTag()"
          />
          <datalist id="untagged-tags">
            <option v-for="name in untagged.tagNames" :key="name" :value="name" />
          </datalist>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 whitespace-nowrap rounded bg-primary px-3 py-1.5 text-sm font-bold text-white disabled:opacity-60"
            :disabled="untagged.busy || !tagInput.trim()"
            @click="applyTag()"
          >
            <Loader2 v-if="untagged.busy" :size="15" class="animate-spin" aria-hidden="true" />
            <CheckCircle2 v-else :size="15" aria-hidden="true" />
            {{ $t("untagged.applyTag") }}
          </button>
          <button
            type="button"
            class="inline-flex items-center gap-1.5 whitespace-nowrap rounded border border-outline px-3 py-1.5 text-sm font-semibold text-on-surface-variant hover:border-error hover:text-error disabled:opacity-60"
            :disabled="untagged.busy"
            @click="confirmDelete()"
          >
            <Trash2 :size="15" aria-hidden="true" />
            {{ $t("common.remove") }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
