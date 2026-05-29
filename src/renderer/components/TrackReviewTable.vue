<script setup lang="ts">
import type {
  AcquisitionJob,
  EventReview,
  EventTrackReview,
  RekordboxTag
} from "../lib/api";
import StatusBadge from "./StatusBadge.vue";

const props = defineProps<{
  activeEvent: EventReview;
  tracks: EventTrackReview[];
  acquisitionJobs: AcquisitionJob[];
  rekordboxTags: RekordboxTag[];
}>();

defineEmits<{
  acceptSuggestedMatch: [track: EventTrackReview];
  assignStagingFile: [track: EventTrackReview, filePath: string];
  updatePermanent: [track: EventTrackReview, permanent: boolean];
  updateTrackTags: [track: EventTrackReview, tags: string];
}>();

function rekordboxTrackTitle(track: EventTrackReview): string {
  if (track.rekordboxTitle) return track.rekordboxTitle;
  if (track.stagingFilePath) return "Staged audio file";
  if (track.rekordboxContentId) return `Rekordbox ${track.rekordboxContentId}`;
  return "No Rekordbox match";
}

function rekordboxTrackDetail(track: EventTrackReview): string {
  if (track.rekordboxArtist) return track.rekordboxArtist;
  if (track.rekordboxFilePath) return track.rekordboxFilePath;
  if (track.stagingFilePath) return track.stagingFilePath;
  return track.reason;
}

function acquisitionJobFor(track: EventTrackReview): AcquisitionJob | undefined {
  return props.acquisitionJobs.find((job) => job.spotifyTrackId === track.spotifyTrackId);
}

function acquisitionLabel(job?: AcquisitionJob): string {
  if (!job) return "";
  return job.status.replace("acquisition_", "").replace("_", " ");
}

function acquisitionTone(job?: AcquisitionJob): "ok" | "warn" | "active" | "muted" {
  if (!job) return "muted";
  if (job.status === "ready" || job.status === "downloaded") return "ok";
  if (job.status === "acquisition_failed" || job.status === "acquisition_ambiguous") {
    return "warn";
  }
  return "active";
}
</script>

<template>
  <div class="overflow-auto rounded-lg border border-outline-variant">
    <table class="w-full min-w-[1120px] border-collapse whitespace-nowrap text-left">
      <thead
        class="sticky top-0 z-10 border-b border-outline-variant bg-surface-container-high font-mono text-[10px] uppercase tracking-wider text-on-surface-variant"
      >
        <tr>
          <th class="px-4 py-3">Requested Track</th>
          <th class="px-4 py-3">Rekordbox Track</th>
          <th class="px-4 py-3">Status</th>
          <th class="px-4 py-3 text-center">Permanent</th>
          <th class="px-4 py-3">Tags</th>
        </tr>
      </thead>
      <tbody class="divide-y divide-outline-variant/50 text-sm">
        <tr
          v-for="track in tracks"
          :key="track.id"
          class="border-l-2 border-transparent bg-surface transition-colors hover:bg-surface-container-high"
          :class="{
            'border-l-primary bg-primary/5': track.status === 'ready' || track.status === 'matched',
            'border-l-tertiary bg-tertiary/5': track.status === 'ambiguous',
            'border-l-error bg-error/5': track.status === 'missing'
          }"
        >
          <td class="px-4 py-3 align-top">
            <strong class="block max-w-[280px] truncate text-on-surface">{{ track.title }}</strong>
            <span class="block max-w-[280px] truncate text-xs text-on-surface-variant">
              {{ track.artists.join(", ") }}
            </span>
          </td>
          <td class="px-4 py-3 align-top">
            <div class="grid gap-2">
              <strong class="max-w-[320px] truncate text-on-surface">
                {{ rekordboxTrackTitle(track) }}
              </strong>
              <span class="block max-w-[320px] truncate text-xs text-on-surface-variant">
                {{ rekordboxTrackDetail(track) }}
              </span>
              <span v-if="track.rekordboxContentId" class="text-xs text-on-surface-variant">
                {{ track.matchMethod ?? "match" }} - {{ track.confidence }}%
              </span>
              <button
                v-if="track.status === 'ambiguous' && track.rekordboxContentId"
                class="w-fit rounded border border-outline bg-surface-container px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="$emit('acceptSuggestedMatch', track)"
              >
                Accept
              </button>
              <select
                v-if="track.status === 'missing' && activeEvent.stagingFiles.length > 0"
                class="max-w-[320px] rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface focus:border-primary focus:outline-none"
                @change="$emit('assignStagingFile', track, ($event.target as HTMLSelectElement).value)"
              >
                <option value="">Assign staged file</option>
                <option
                  v-for="file in activeEvent.stagingFiles"
                  :key="file.filePath"
                  :value="file.filePath"
                >
                  {{ file.title }} - {{ file.artist || file.filePath }}
                </option>
              </select>
            </div>
          </td>
          <td class="px-4 py-3 align-top">
            <div class="grid justify-items-start gap-2">
              <StatusBadge
                :tone="
                  track.status === 'ready' || track.status === 'matched' || track.status === 'applied'
                    ? 'ok'
                    : track.status === 'missing' || track.status === 'ambiguous'
                      ? 'warn'
                      : 'neutral'
                "
              >
                {{ track.status }}
              </StatusBadge>
              <StatusBadge
                v-if="acquisitionJobFor(track)"
                :tone="acquisitionTone(acquisitionJobFor(track))"
              >
                {{ acquisitionLabel(acquisitionJobFor(track)) }}
              </StatusBadge>
              <span v-if="acquisitionJobFor(track)?.error" class="max-w-[220px] text-xs text-tertiary">
                {{ acquisitionJobFor(track)?.error }}
              </span>
            </div>
          </td>
          <td class="px-4 py-3 text-center align-top">
            <input
              class="h-4 w-4 rounded border-outline-variant bg-surface accent-primary"
              type="checkbox"
              :checked="track.permanent"
              @change="$emit('updatePermanent', track, ($event.target as HTMLInputElement).checked)"
            />
          </td>
          <td class="px-4 py-3 align-top">
            <input
              class="w-64 rounded border border-outline bg-surface-container px-3 py-2 text-xs text-on-surface focus:border-primary focus:outline-none"
              :value="track.tags.join(', ')"
              list="review-rekordbox-tags"
              placeholder="Existing MyTags"
              @change="$emit('updateTrackTags', track, ($event.target as HTMLInputElement).value)"
            />
          </td>
        </tr>
        <tr v-if="tracks.length === 0">
          <td class="px-4 py-6 text-on-surface-variant" colspan="5">
            No tracks for this filter.
          </td>
        </tr>
      </tbody>
    </table>
    <datalist id="review-rekordbox-tags">
      <option v-for="tagItem in rekordboxTags" :key="tagItem.id" :value="tagItem.name" />
    </datalist>
  </div>
</template>

