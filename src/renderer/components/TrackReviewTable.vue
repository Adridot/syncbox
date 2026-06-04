<script setup lang="ts">
import { ChevronLeft, ChevronRight, Eye, EyeOff, Search } from "@lucide/vue";
import { computed, ref, watch } from "vue";
import type { AcquisitionJob, StagingFile, TrackReview } from "../lib/api";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  tracks: TrackReview[];
  acquisitionJobs?: AcquisitionJob[];   // events: per-track job display
  stagingFiles?: StagingFile[];          // events: manual file assignment
  selectedIds?: string[];                // library: batch selection
  showTagColumn?: boolean;               // library: tags column
}>();

const emit = defineEmits<{
  acceptSuggestedMatch: [track: TrackReview];
  assignStagingFile: [track: TrackReview, path: string];
  searchDeezer: [track: TrackReview];
  ignore: [track: TrackReview];
  unignore: [track: TrackReview];
  toggleSelect: [track: TrackReview, checked: boolean];
  toggleSelectAll: [tracks: TrackReview[], checked: boolean];
}>();

const PAGE_SIZE = 20;
const filter = ref<"actionable" | "ready" | "all">("actionable");
const currentPage = ref(1);

const EXCLUDED_FROM_ACTIONABLE = new Set(["imported", "applied", "removed_from_source", "ignored"]);

// In the Actionable view, float the tracks that actually need a decision to the
// top: missing first, then ambiguous, then everything else (ready/matched…).
// Lower rank = higher in the list.
const ACTIONABLE_RANK: Record<string, number> = { missing: 0, ambiguous: 1 };
const actionableRank = (status: string): number => ACTIONABLE_RANK[status] ?? 2;

const filteredTracks = computed(() => {
  if (filter.value === "actionable") {
    return props.tracks
      .filter((t) => !EXCLUDED_FROM_ACTIONABLE.has(t.status))
      // Stable sort keeps the original order within each rank.
      .sort((a, b) => actionableRank(a.status) - actionableRank(b.status));
  }
  if (filter.value === "ready") return props.tracks.filter((t) => t.status === "ready" || t.status === "matched");
  return props.tracks;
});

const totalPages = computed(() => Math.max(1, Math.ceil(filteredTracks.value.length / PAGE_SIZE)));

const paginatedTracks = computed(() => {
  const page = Math.min(currentPage.value, totalPages.value);
  return filteredTracks.value.slice((page - 1) * PAGE_SIZE, page * PAGE_SIZE);
});

watch(filter, () => { currentPage.value = 1; });
watch(() => props.tracks.length, () => { currentPage.value = 1; });

const allPageSelected = computed(() => {
  if (!props.selectedIds || paginatedTracks.value.length === 0) return false;
  const sel = new Set(props.selectedIds);
  return paginatedTracks.value.every((t) => sel.has(t.spotifyTrackId));
});

function setFilter(f: "actionable" | "ready" | "all"): void {
  filter.value = f;
}

function rekordboxTitle(track: TrackReview): string {
  if (track.rekordboxTitle) return track.rekordboxTitle;
  if (track.stagingFilePath) return "Downloaded audio file";
  if (track.rekordboxContentId) return `Rekordbox ${track.rekordboxContentId}`;
  return "No Rekordbox match";
}

function rekordboxDetail(track: TrackReview): string {
  if (track.rekordboxArtist) return track.rekordboxArtist;
  if (track.rekordboxFilePath) return track.rekordboxFilePath;
  if (track.stagingFilePath) return track.stagingFilePath.split(/[\\/]/).pop() ?? track.stagingFilePath;
  return track.reason;
}

function statusTone(status: string): "ok" | "warn" | "active" | "muted" | "neutral" {
  if (status === "ready" || status === "matched" || status === "applied" || status === "imported") return "ok";
  if (status === "missing" || status === "conflict" || status === "ambiguous" || status === "acquisition_failed") return "warn";
  if (status === "new" || status === "downloading" || status === "queued") return "active";
  if (status === "ignored" || status === "removed_from_source") return "muted";
  return "neutral";
}

function jobFor(track: TrackReview): AcquisitionJob | undefined {
  return props.acquisitionJobs?.find((j) => j.spotifyTrackId === track.spotifyTrackId);
}

function jobLabel(job?: AcquisitionJob): string {
  if (!job) return "";
  return job.status.replace("acquisition_", "").replace("_", " ");
}

function jobTone(job?: AcquisitionJob): "ok" | "warn" | "active" | "muted" {
  if (!job) return "muted";
  if (job.status === "ready" || job.status === "downloaded") return "ok";
  if (job.status === "acquisition_failed" || job.status === "acquisition_ambiguous") return "warn";
  return "active";
}
</script>

<template>
  <div class="flex flex-col gap-2">
    <!-- Filter tabs + count -->
    <div class="flex flex-wrap items-center gap-2">
      <button
        v-for="f in (['actionable', 'ready', 'all'] as const)"
        :key="f"
        class="rounded border px-3 py-1.5 text-xs font-bold capitalize transition-colors"
        :class="filter === f
          ? 'border-primary bg-primary/10 text-primary'
          : 'border-outline bg-surface-container-high text-on-surface-variant hover:text-on-surface'"
        type="button"
        @click="setFilter(f)"
      >
        {{ f }}
      </button>
      <span class="ml-auto text-xs text-on-surface-variant">
        {{ filteredTracks.length }} track{{ filteredTracks.length !== 1 ? "s" : "" }}
      </span>
    </div>

    <!-- Table -->
    <div class="overflow-auto rounded-lg border border-outline-variant">
      <table class="w-full min-w-[900px] border-collapse whitespace-nowrap text-left">
        <thead class="sticky top-0 z-10 border-b border-outline-variant bg-surface-container-high font-mono text-[10px] uppercase tracking-wider text-on-surface-variant">
          <tr>
            <th v-if="selectedIds !== undefined" class="px-4 py-3">
              <input
                class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
                type="checkbox"
                :checked="allPageSelected"
                @change="emit('toggleSelectAll', paginatedTracks, ($event.target as HTMLInputElement).checked)"
              />
            </th>
            <th class="px-4 py-3">Requested Track</th>
            <th class="px-4 py-3">Rekordbox / File</th>
            <th class="px-4 py-3">Status</th>
            <th v-if="showTagColumn" class="px-4 py-3">Tags</th>
            <th class="px-4 py-3"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-outline-variant/50 text-sm">
          <tr
            v-for="track in paginatedTracks"
            :key="track.id"
            class="border-l-2 border-transparent bg-surface transition-colors hover:bg-surface-container-high"
            :class="{
              'border-l-primary bg-primary/5': track.status === 'ready' || track.status === 'matched',
              'border-l-tertiary bg-tertiary/5': track.status === 'new' || track.status === 'missing' || track.status === 'conflict' || track.status === 'ambiguous',
              'border-l-error bg-error/5': track.status === 'acquisition_failed',
              'opacity-50': track.status === 'ignored'
            }"
          >
            <!-- Checkbox (library only) -->
            <td v-if="selectedIds !== undefined" class="px-4 py-3 align-top">
              <input
                class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
                type="checkbox"
                :checked="selectedIds.includes(track.spotifyTrackId)"
                @change="emit('toggleSelect', track, ($event.target as HTMLInputElement).checked)"
              />
            </td>

            <!-- Spotify track -->
            <td class="px-4 py-3 align-top">
              <strong class="block max-w-[300px] truncate text-on-surface">{{ track.title }}</strong>
              <span class="block max-w-[300px] truncate text-xs text-on-surface-variant">
                {{ track.artists.join(", ") }}
              </span>
            </td>

            <!-- Rekordbox / File -->
            <td class="px-4 py-3 align-top">
              <div class="grid gap-1">
                <strong class="block max-w-[340px] truncate text-on-surface">{{ rekordboxTitle(track) }}</strong>
                <span class="block max-w-[340px] truncate text-xs text-on-surface-variant">
                  {{ rekordboxDetail(track) }}
                </span>
                <span v-if="track.rekordboxContentId" class="text-xs text-on-surface-variant">
                  {{ track.matchMethod ?? "match" }} — {{ track.confidence }}%
                </span>
                <!-- Accept match (events: ambiguous) -->
                <button
                  v-if="track.status === 'ambiguous' && track.rekordboxContentId"
                  class="w-fit rounded border border-outline bg-surface-container px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="emit('acceptSuggestedMatch', track)"
                >
                  Accept
                </button>
                <!-- Staging file assignment (events only) -->
                <select
                  v-if="stagingFiles !== undefined && track.status === 'missing' && stagingFiles.length > 0"
                  class="max-w-[340px] rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface focus:border-primary focus:outline-none"
                  @change="emit('assignStagingFile', track, ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">Assign staged file</option>
                  <option v-for="file in stagingFiles" :key="file.filePath" :value="file.filePath">
                    {{ file.title }} — {{ file.artist || file.filePath }}
                  </option>
                </select>
                <p
                  v-if="stagingFiles !== undefined && track.status === 'missing' && stagingFiles.length === 0"
                  class="max-w-[340px] rounded border border-dashed border-outline bg-surface-container/50 px-3 py-2 text-[11px] leading-relaxed text-on-surface-variant"
                >
                  Not found on Deezer. Add the audio file manually to the event folder and click
                  <strong class="text-on-surface">Refresh Folder</strong>.
                </p>
              </div>
            </td>

            <!-- Status -->
            <td class="px-4 py-3 align-top">
              <div class="grid justify-items-start gap-2">
                <StatusBadge :tone="statusTone(track.status)">
                  {{ track.status.replaceAll("_", " ") }}
                </StatusBadge>
                <template v-if="acquisitionJobs !== undefined">
                  <StatusBadge v-if="jobFor(track)" :tone="jobTone(jobFor(track))">
                    {{ jobLabel(jobFor(track)) }}
                  </StatusBadge>
                  <span v-if="jobFor(track)?.error" class="max-w-[220px] text-xs text-tertiary">
                    {{ jobFor(track)?.error }}
                  </span>
                </template>
              </div>
            </td>

            <!-- Tags column (library only) -->
            <td v-if="showTagColumn" class="px-4 py-3 align-top">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in track.tags"
                  :key="tag"
                  class="rounded bg-secondary/10 px-1.5 py-0.5 text-[10px] font-bold text-secondary"
                >
                  {{ tag }}
                </span>
              </div>
            </td>

            <!-- Actions -->
            <td class="px-4 py-3 align-top">
              <div class="flex gap-1.5">
                <button
                  v-if="track.status === 'new' || track.status === 'missing'"
                  class="inline-flex items-center gap-1 rounded border border-outline bg-surface-container px-2 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  :title="`Search Deezer for: ${track.title}`"
                  @click="emit('searchDeezer', track)"
                >
                  <Search :size="12" aria-hidden="true" />
                  Search
                </button>
                <button
                  v-if="track.status === 'new' || track.status === 'missing'"
                  class="inline-flex items-center gap-1 rounded border border-outline bg-surface-container px-2 py-1 text-[11px] font-bold text-on-surface-variant transition-colors hover:border-outline-variant"
                  type="button"
                  title="Ignore this track"
                  @click="emit('ignore', track)"
                >
                  <EyeOff :size="12" aria-hidden="true" />
                  Ignore
                </button>
                <button
                  v-if="track.status === 'ignored'"
                  class="inline-flex items-center gap-1 rounded border border-secondary/40 bg-secondary/10 px-2 py-1 text-[11px] font-bold text-secondary transition-colors hover:border-secondary"
                  type="button"
                  title="Restore this track"
                  @click="emit('unignore', track)"
                >
                  <Eye :size="12" aria-hidden="true" />
                  Restore
                </button>
              </div>
            </td>
          </tr>
          <tr v-if="paginatedTracks.length === 0">
            <td
              class="px-4 py-6 text-on-surface-variant"
              :colspan="(selectedIds !== undefined ? 1 : 0) + 3 + (showTagColumn ? 1 : 0) + 1"
            >
              No tracks for this filter.
            </td>
          </tr>
        </tbody>
      </table>

      <!-- Pagination -->
      <div v-if="totalPages > 1" class="flex items-center justify-between border-t border-outline-variant px-4 py-3">
        <span class="text-xs text-on-surface-variant">
          Page {{ Math.min(currentPage, totalPages) }} / {{ totalPages }} · {{ filteredTracks.length }} tracks
        </span>
        <div class="flex gap-1">
          <button
            class="grid h-7 w-7 place-items-center rounded border border-outline bg-surface-container text-on-surface-variant transition-colors hover:border-primary disabled:opacity-40"
            type="button"
            :disabled="currentPage <= 1"
            @click="currentPage--"
          >
            <ChevronLeft :size="14" aria-hidden="true" />
          </button>
          <button
            v-for="p in totalPages"
            :key="p"
            class="grid h-7 w-7 place-items-center rounded border text-xs font-bold transition-colors"
            :class="p === Math.min(currentPage, totalPages)
              ? 'border-primary bg-primary/10 text-primary'
              : 'border-outline bg-surface-container text-on-surface-variant hover:border-primary'"
            type="button"
            @click="currentPage = p"
          >
            {{ p }}
          </button>
          <button
            class="grid h-7 w-7 place-items-center rounded border border-outline bg-surface-container text-on-surface-variant transition-colors hover:border-primary disabled:opacity-40"
            type="button"
            :disabled="currentPage >= totalPages"
            @click="currentPage++"
          >
            <ChevronRight :size="14" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>
