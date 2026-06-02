<script setup lang="ts">
import {
  AlertTriangle,
  DownloadCloud,
  FileSearch,
  Link2,
  Loader2,
  Search,
  ShieldCheck,
  Trash2,
} from "@lucide/vue";
import { ref } from "vue";
import type { MissingTrack } from "../lib/api";
import { useMissingStore } from "../stores/missing";
import { useSystemStore } from "../stores/system";

const missing = useMissingStore();
const system = useSystemStore();

// Which track currently has its relink-candidate panel open.
const relinkOpenId = ref<string | null>(null);

function isBusy(track: MissingTrack, action: string): boolean {
  return missing.busyId === track.contentId && missing.busyAction === action;
}

function anyBusyFor(track: MissingTrack): boolean {
  // Locked while an action runs, or once a re-download has been queued for it.
  return missing.busyId === track.contentId || missing.queued.has(track.contentId);
}

async function toggleRelink(track: MissingTrack): Promise<void> {
  if (relinkOpenId.value === track.contentId) {
    relinkOpenId.value = null;
    return;
  }
  relinkOpenId.value = track.contentId;
  if (!missing.candidates[track.contentId]) {
    await missing.loadCandidates(track);
  }
}

async function confirmRedownload(track: MissingTrack): Promise<void> {
  if (
    window.confirm(
      `Re-download “${track.artist} – ${track.title}” from Deezer into your permanent folder?\n\nThis is queued as a download job — watch its progress in Download & Match. When it finishes it automatically re-links the collection entry (Rekordbox must be closed for the re-link).`
    )
  ) {
    await missing.redownload(track);
  }
}

async function confirmRemove(track: MissingTrack): Promise<void> {
  if (
    window.confirm(
      `Remove “${track.artist || "?"} – ${track.title || "?"}” from the Rekordbox collection?\n\nThe entry is soft-deleted (reversible from Doctor → backups).`
    )
  ) {
    await missing.remove(track);
  }
}
</script>

<template>
  <div class="h-full overflow-y-auto px-6 py-6 md:px-8">
    <div class="mx-auto flex max-w-4xl flex-col gap-6">
      <!-- Controls -->
      <section
        class="flex flex-wrap items-center gap-4 rounded-xl border border-outline-variant bg-surface-container p-5"
      >
        <div class="flex items-center gap-2 text-sm text-on-surface-variant">
          <FileSearch :size="18" aria-hidden="true" />
          Find collection entries whose audio file no longer exists on disk.
        </div>
        <button
          type="button"
          class="ml-auto inline-flex items-center gap-2 rounded bg-primary px-4 py-2 text-sm font-bold text-white disabled:opacity-60"
          :disabled="missing.scanning || !system.api"
          @click="missing.scan()"
        >
          <Loader2 v-if="missing.scanning" :size="15" class="animate-spin" aria-hidden="true" />
          <Search v-else :size="15" aria-hidden="true" />
          Scan collection
        </button>
      </section>

      <p
        v-if="missing.scanned && !missing.unavailableReason"
        class="text-sm text-on-surface-variant"
      >
        <strong class="text-on-surface">{{ missing.tracks.length }}</strong>
        missing file(s) out of
        <strong class="text-on-surface">{{ missing.total }}</strong>
        collection tracks.
      </p>

      <p
        v-if="missing.unavailableReason"
        class="rounded-xl border border-error/40 bg-error/5 px-5 py-4 text-sm text-error"
      >
        {{ missing.unavailableReason }}
      </p>

      <p
        v-else-if="missing.scanned && missing.tracks.length === 0"
        class="rounded-xl border border-outline-variant bg-surface-container px-5 py-8 text-center text-sm text-on-surface-variant"
      >
        ✅ Every collection entry points to an existing file.
      </p>

      <p
        v-else-if="!missing.scanned"
        class="rounded-xl border border-dashed border-outline-variant px-5 py-10 text-center text-sm text-on-surface-variant"
      >
        Scan to list entries Rekordbox would mark with a “!” — with per-track re-download,
        re-link or removal.
      </p>

      <!-- Missing tracks -->
      <section
        v-for="track in missing.tracks"
        :key="track.contentId"
        class="rounded-xl border border-outline-variant bg-surface-container"
      >
        <div class="flex items-start gap-3 px-5 py-3">
          <AlertTriangle :size="18" class="mt-0.5 shrink-0 text-tertiary" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <strong class="truncate text-sm text-on-surface">
                {{ track.title || "(no title)" }}
              </strong>
              <span
                v-if="track.protected"
                class="inline-flex items-center gap-0.5 rounded bg-secondary/15 px-1.5 py-0.5 text-[10px] font-semibold text-secondary"
              >
                <ShieldCheck :size="11" aria-hidden="true" /> Permanent
              </span>
              <span
                v-if="track.fileType"
                class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
              >
                {{ track.fileType }}
              </span>
              <span
                v-if="track.playlistCount"
                class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
              >
                {{ track.playlistCount }} playlists
              </span>
              <span
                v-if="track.tagCount"
                class="rounded bg-surface-container-high px-1.5 py-0.5 text-[10px] text-on-surface-variant"
              >
                {{ track.tagCount }} tags
              </span>
              <span
                v-if="!track.isrc"
                class="rounded bg-error/15 px-1.5 py-0.5 text-[10px] font-semibold text-error"
              >
                no ISRC
              </span>
              <span
                v-if="missing.queued.has(track.contentId)"
                class="inline-flex items-center gap-0.5 rounded bg-primary/15 px-1.5 py-0.5 text-[10px] font-semibold text-primary"
              >
                <Loader2 :size="10" class="animate-spin" aria-hidden="true" /> Re-download queued
              </span>
            </div>
            <p class="truncate text-xs text-on-surface-variant">{{ track.artist || "—" }}</p>
            <p class="mt-0.5 truncate text-[10px] text-on-surface-variant/70" :title="track.filePath ?? ''">
              {{ track.filePath }}
            </p>
          </div>

          <div class="flex shrink-0 items-center gap-1.5">
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded bg-primary px-2.5 py-1 text-xs font-bold text-white disabled:opacity-60"
              :disabled="anyBusyFor(track)"
              :title="track.isrc ? 'Re-download via ISRC' : 'Re-download via title/artist search'"
              @click="confirmRedownload(track)"
            >
              <Loader2 v-if="isBusy(track, 'redownload')" :size="13" class="animate-spin" aria-hidden="true" />
              <DownloadCloud v-else :size="13" aria-hidden="true" />
              Re-download
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded border border-outline px-2.5 py-1 text-xs font-semibold text-on-surface hover:border-primary disabled:opacity-60"
              :disabled="anyBusyFor(track)"
              @click="toggleRelink(track)"
            >
              <Link2 :size="13" aria-hidden="true" />
              Re-link
            </button>
            <button
              type="button"
              class="inline-flex items-center gap-1 rounded border border-outline px-2.5 py-1 text-xs font-semibold text-on-surface-variant hover:border-error hover:text-error disabled:opacity-60"
              :disabled="anyBusyFor(track)"
              @click="confirmRemove(track)"
            >
              <Loader2 v-if="isBusy(track, 'remove')" :size="13" class="animate-spin" aria-hidden="true" />
              <Trash2 v-else :size="13" aria-hidden="true" />
              Remove
            </button>
          </div>
        </div>

        <!-- Relink candidate panel -->
        <div
          v-if="relinkOpenId === track.contentId"
          class="border-t border-outline-variant bg-surface-container-high/40 px-5 py-3"
        >
          <p class="mb-2 text-xs font-semibold text-on-surface-variant">
            Existing files found on disk that match this track:
          </p>
          <p
            v-if="missing.candidatesLoading === track.contentId"
            class="flex items-center gap-2 text-xs text-on-surface-variant"
          >
            <Loader2 :size="13" class="animate-spin" aria-hidden="true" /> Searching…
          </p>
          <p
            v-else-if="(missing.candidates[track.contentId]?.length ?? 0) === 0"
            class="text-xs text-on-surface-variant"
          >
            No matching file found in your storage folders. Try “Re-download” instead.
          </p>
          <ul v-else class="space-y-1">
            <li
              v-for="candidate in missing.candidates[track.contentId]"
              :key="candidate.filePath"
              class="flex items-center gap-2 rounded border border-outline-variant bg-surface px-3 py-1.5"
            >
              <span
                class="rounded px-1.5 py-0.5 text-[10px] font-semibold"
                :class="candidate.score >= 100 ? 'bg-secondary/15 text-secondary' : 'bg-tertiary/15 text-tertiary'"
              >
                {{ candidate.reason }} · {{ candidate.score }}%
              </span>
              <span class="min-w-0 flex-1 truncate text-xs text-on-surface" :title="candidate.filePath">
                {{ candidate.fileName }}
              </span>
              <button
                type="button"
                class="inline-flex shrink-0 items-center gap-1 rounded bg-primary px-2.5 py-1 text-[11px] font-bold text-white disabled:opacity-60"
                :disabled="anyBusyFor(track)"
                @click="missing.relink(track, candidate.filePath)"
              >
                <Loader2 v-if="isBusy(track, 'relink')" :size="12" class="animate-spin" aria-hidden="true" />
                <Link2 v-else :size="12" aria-hidden="true" />
                Use this file
              </button>
            </li>
          </ul>
        </div>
      </section>
    </div>
  </div>
</template>
