<script setup lang="ts">
import { Eye, EyeOff, Search } from "@lucide/vue";
import { useVirtualizer } from "@tanstack/vue-virtual";
import { computed, ref, watch, type ComponentPublicInstance } from "vue";
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

const filter = ref<"actionable" | "ready" | "all">("actionable");

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

function setFilter(f: "actionable" | "ready" | "all"): void {
  filter.value = f;
}

const allFilteredSelected = computed(() => {
  if (!props.selectedIds || filteredTracks.value.length === 0) return false;
  const sel = new Set(props.selectedIds);
  return filteredTracks.value.every((t) => sel.has(t.spotifyTrackId));
});

// --- Virtualisation --------------------------------------------------------
// The list replaces the old 20-per-page pagination: every filtered row is now
// scrollable in one container, but only the visible rows (+overscan) are
// mounted. Rows have variable height (staging selects, multi-line errors,
// action buttons) so we let the virtualizer measure each rendered row instead
// of assuming a fixed height.
const parentRef = ref<HTMLElement | null>(null);
const rowVirtualizer = useVirtualizer(
  computed(() => ({
    count: filteredTracks.value.length,
    getScrollElement: () => parentRef.value,
    estimateSize: () => 96,
    overscan: 10,
  })),
);
const virtualRows = computed(() => rowVirtualizer.value.getVirtualItems());
const totalSize = computed(() => rowVirtualizer.value.getTotalSize());
function measureRow(el: Element | ComponentPublicInstance | null): void {
  if (el instanceof Element) rowVirtualizer.value.measureElement(el);
}

// Switching filter OR swapping the track list (new source selected) — jump
// back to the top so the user doesn't land mid-scroll on unrelated rows.
watch(filter, () => parentRef.value?.scrollTo({ top: 0 }));
watch(() => props.tracks, () => parentRef.value?.scrollTo({ top: 0 }));

// Shared column template for the header and every row so they stay aligned.
const gridCols = computed(() => {
  const cols: string[] = [];
  if (props.selectedIds !== undefined) cols.push("3rem");
  cols.push("minmax(220px,1.2fr)"); // requested track
  cols.push("minmax(260px,1.4fr)"); // rekordbox / file
  cols.push("minmax(180px,15rem)"); // status
  if (props.showTagColumn) cols.push("minmax(120px,0.8fr)"); // tags
  cols.push("minmax(140px,auto)"); // actions
  return cols.join(" ");
});

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

const jobsByTrackId = computed(() => {
  const map = new Map<string, AcquisitionJob>();
  for (const job of props.acquisitionJobs ?? []) map.set(job.spotifyTrackId, job);
  return map;
});

function jobFor(track: TrackReview): AcquisitionJob | undefined {
  return jobsByTrackId.value.get(track.spotifyTrackId);
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

// One badge per track instead of two (track status + job status, which mostly
// duplicated each other). For a still-"missing" track the download job is the
// live signal (queued → downloading → downloaded/ready, or failed/ambiguous) so
// show it; otherwise the track status already says it all.
function displayStatus(track: TrackReview): {
  label: string;
  tone: "ok" | "warn" | "active" | "muted" | "neutral";
} {
  const job = jobFor(track);
  if (track.status === "missing" && job) {
    return { label: jobLabel(job), tone: jobTone(job) };
  }
  return { label: track.status.replaceAll("_", " "), tone: statusTone(track.status) };
}

function jobError(track: TrackReview): string | undefined {
  return jobFor(track)?.error ?? undefined;
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

    <!-- Virtualised list -->
    <div
      ref="parentRef"
      class="max-h-[70vh] overflow-auto rounded-lg border border-outline-variant"
    >
      <div class="min-w-[900px]">
        <!-- Sticky header -->
        <div
          class="sticky top-0 z-10 grid items-center border-b border-outline-variant bg-surface-container-high font-mono text-[10px] uppercase tracking-wider text-on-surface-variant"
          :style="{ gridTemplateColumns: gridCols }"
        >
          <div v-if="selectedIds !== undefined" class="px-4 py-3">
            <input
              class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
              type="checkbox"
              :checked="allFilteredSelected"
              @change="emit('toggleSelectAll', filteredTracks, ($event.target as HTMLInputElement).checked)"
            />
          </div>
          <div class="px-4 py-3">Requested Track</div>
          <div class="px-4 py-3">Rekordbox / File</div>
          <div class="px-4 py-3">Status</div>
          <div v-if="showTagColumn" class="px-4 py-3">Tags</div>
          <div class="px-4 py-3"></div>
        </div>

        <!-- Empty state -->
        <div
          v-if="filteredTracks.length === 0"
          class="px-4 py-6 text-sm text-on-surface-variant"
        >
          No tracks for this filter.
        </div>

        <!-- Virtual rows -->
        <div v-else :style="{ height: `${totalSize}px`, position: 'relative' }">
          <div
            v-for="vrow in virtualRows"
            :key="filteredTracks[vrow.index].id"
            :ref="measureRow"
            :data-index="vrow.index"
            class="grid items-start border-b border-l-2 border-outline-variant/50 border-l-transparent bg-surface text-sm transition-colors hover:bg-surface-container-high"
            :class="{
              'border-l-primary bg-primary/5': filteredTracks[vrow.index].status === 'ready' || filteredTracks[vrow.index].status === 'matched',
              'border-l-tertiary bg-tertiary/5': filteredTracks[vrow.index].status === 'new' || filteredTracks[vrow.index].status === 'missing' || filteredTracks[vrow.index].status === 'conflict' || filteredTracks[vrow.index].status === 'ambiguous',
              'border-l-error bg-error/5': filteredTracks[vrow.index].status === 'acquisition_failed',
              'opacity-50': filteredTracks[vrow.index].status === 'ignored',
            }"
            :style="{
              position: 'absolute',
              top: 0,
              left: 0,
              width: '100%',
              transform: `translateY(${vrow.start}px)`,
              gridTemplateColumns: gridCols,
            }"
          >
            <!-- Checkbox (library only) -->
            <div v-if="selectedIds !== undefined" class="px-4 py-3">
              <input
                class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
                type="checkbox"
                :checked="selectedIds.includes(filteredTracks[vrow.index].spotifyTrackId)"
                @change="emit('toggleSelect', filteredTracks[vrow.index], ($event.target as HTMLInputElement).checked)"
              />
            </div>

            <!-- Spotify track -->
            <div class="px-4 py-3">
              <strong class="block max-w-[300px] truncate text-on-surface">{{ filteredTracks[vrow.index].title }}</strong>
              <span class="block max-w-[300px] truncate text-xs text-on-surface-variant">
                {{ filteredTracks[vrow.index].artists.join(", ") }}
              </span>
            </div>

            <!-- Rekordbox / File -->
            <div class="px-4 py-3">
              <div class="grid gap-1">
                <strong class="block max-w-[340px] truncate text-on-surface">{{ rekordboxTitle(filteredTracks[vrow.index]) }}</strong>
                <span class="block max-w-[340px] truncate text-xs text-on-surface-variant">
                  {{ rekordboxDetail(filteredTracks[vrow.index]) }}
                </span>
                <span v-if="filteredTracks[vrow.index].rekordboxContentId" class="text-xs text-on-surface-variant">
                  {{ filteredTracks[vrow.index].matchMethod ?? "match" }} — {{ filteredTracks[vrow.index].confidence }}%
                </span>
                <!-- Accept match (events: ambiguous) -->
                <button
                  v-if="filteredTracks[vrow.index].status === 'ambiguous' && filteredTracks[vrow.index].rekordboxContentId"
                  class="w-fit rounded border border-outline bg-surface-container px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="emit('acceptSuggestedMatch', filteredTracks[vrow.index])"
                >
                  Accept
                </button>
                <!-- Staging file assignment (events only) -->
                <select
                  v-if="stagingFiles !== undefined && filteredTracks[vrow.index].status === 'missing' && stagingFiles.length > 0"
                  class="max-w-[340px] rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface focus:border-primary focus:outline-none"
                  @change="emit('assignStagingFile', filteredTracks[vrow.index], ($event.target as HTMLSelectElement).value)"
                >
                  <option value="">Assign staged file</option>
                  <option v-for="file in stagingFiles" :key="file.filePath" :value="file.filePath">
                    {{ file.title }} — {{ file.artist || file.filePath }}
                  </option>
                </select>
                <p
                  v-if="stagingFiles !== undefined && filteredTracks[vrow.index].status === 'missing' && stagingFiles.length === 0"
                  class="max-w-[340px] rounded border border-dashed border-outline bg-surface-container/50 px-3 py-2 text-[11px] leading-relaxed text-on-surface-variant"
                >
                  Not found on Deezer. Add the audio file manually to the event folder and click
                  <strong class="text-on-surface">Refresh Folder</strong>.
                </p>
              </div>
            </div>

            <!-- Status -->
            <div class="px-4 py-3">
              <div class="grid max-w-[240px] justify-items-start gap-1.5">
                <StatusBadge :tone="displayStatus(filteredTracks[vrow.index]).tone">
                  {{ displayStatus(filteredTracks[vrow.index]).label }}
                </StatusBadge>
                <span
                  v-if="jobError(filteredTracks[vrow.index])"
                  class="line-clamp-2 w-[220px] whitespace-normal break-words text-[11px] leading-snug text-tertiary"
                  :title="jobError(filteredTracks[vrow.index])"
                >
                  {{ jobError(filteredTracks[vrow.index]) }}
                </span>
              </div>
            </div>

            <!-- Tags column (library only) -->
            <div v-if="showTagColumn" class="px-4 py-3">
              <div class="flex flex-wrap gap-1">
                <span
                  v-for="tag in filteredTracks[vrow.index].tags"
                  :key="tag"
                  class="rounded bg-secondary/10 px-1.5 py-0.5 text-[10px] font-bold text-secondary"
                >
                  {{ tag }}
                </span>
              </div>
            </div>

            <!-- Actions -->
            <div class="px-4 py-3">
              <div class="flex gap-1.5">
                <button
                  v-if="filteredTracks[vrow.index].status === 'new' || filteredTracks[vrow.index].status === 'missing'"
                  class="inline-flex items-center gap-1 rounded border border-outline bg-surface-container px-2 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  :title="`Search Deezer for: ${filteredTracks[vrow.index].title}`"
                  @click="emit('searchDeezer', filteredTracks[vrow.index])"
                >
                  <Search :size="12" aria-hidden="true" />
                  Search
                </button>
                <button
                  v-if="filteredTracks[vrow.index].status === 'new' || filteredTracks[vrow.index].status === 'missing'"
                  class="inline-flex items-center gap-1 rounded border border-outline bg-surface-container px-2 py-1 text-[11px] font-bold text-on-surface-variant transition-colors hover:border-outline-variant"
                  type="button"
                  title="Ignore this track"
                  @click="emit('ignore', filteredTracks[vrow.index])"
                >
                  <EyeOff :size="12" aria-hidden="true" />
                  Ignore
                </button>
                <button
                  v-if="filteredTracks[vrow.index].status === 'ignored'"
                  class="inline-flex items-center gap-1 rounded border border-secondary/40 bg-secondary/10 px-2 py-1 text-[11px] font-bold text-secondary transition-colors hover:border-secondary"
                  type="button"
                  title="Restore this track"
                  @click="emit('unignore', filteredTracks[vrow.index])"
                >
                  <Eye :size="12" aria-hidden="true" />
                  Restore
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
