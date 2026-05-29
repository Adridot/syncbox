<script setup lang="ts">
import { AlertTriangle, CheckCircle2, Clock, FileAudio, RefreshCw, Search } from "@lucide/vue";
import { computed } from "vue";
import type { GlobalAcquisitionJob } from "../lib/api";
import StatusBadge from "../components/StatusBadge.vue";
import { useEventsStore } from "../stores/events";
import { useLibraryStore } from "../stores/library";
import { useProposalsStore } from "../stores/proposals";
import { useSystemStore } from "../stores/system";
import { useUiStore } from "../stores/ui";

const ui = useUiStore();
const system = useSystemStore();
const events = useEventsStore();
const library = useLibraryStore();
const proposals = useProposalsStore();

const pendingProposals = computed(() =>
  proposals.proposals.filter((p) => p.status === "pending")
);
const conflictTracks = computed(() =>
  events.activeEvent?.tracks.filter((t) => t.status === "ambiguous") ?? []
);
const libraryConflictTracks = computed(() =>
  library.activeReview?.tracks.filter((t) => t.status === "conflict") ?? []
);

function acquisitionTrackTitle(job: GlobalAcquisitionJob): string {
  return `${job.trackTitle} - ${job.trackArtists.join(", ") || job.sourceName}`;
}

function acquisitionDetail(job: GlobalAcquisitionJob): string {
  if (job.error) return job.error;
  if (job.deezerTrackId) {
    return `${job.matchMethod ?? "match"} - ${job.confidence}% - Deezer ${job.deezerTrackId}`;
  }
  return job.outputDir ?? job.spotifyTrackId;
}

function jobTone(job: GlobalAcquisitionJob): "ok" | "warn" | "active" | "muted" {
  if (job.status === "ready" || job.status === "downloaded") return "ok";
  if (job.status === "acquisition_failed" || job.status === "acquisition_ambiguous") return "warn";
  if (["queued", "downloading", "resolved"].includes(job.status)) return "active";
  return "muted";
}

const proposalLabels: Record<string, string> = {
  remove_from_rekordbox: "Remove from Rekordbox",
  protect_manual_track: "Protected — manual collection",
  manual_match: "Manual match needed",
  add_to_rekordbox: "Missing from Rekordbox",
};

function proposalLabel(type: string): string {
  return proposalLabels[type] ?? type;
}

async function openEventInEvents(event: { id: number; eventName: string }): Promise<void> {
  const summary = events.summaries.find((s) => s.id === event.id);
  if (summary) await events.openEvent(summary);
  ui.navigateTo("events");
}
</script>

<template>
  <div class="h-full overflow-y-auto p-6 md:p-8">
    <div class="mx-auto flex w-full max-w-[1600px] flex-col gap-8 lg:flex-row">
      <section class="min-w-0 flex-1">
        <div class="mb-6 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h2 class="mb-1 text-2xl font-bold text-on-surface md:text-3xl">
              Download & Match Center
            </h2>
            <p class="text-sm text-on-surface-variant">
              Deemix queue, staged files, and metadata conflicts.
            </p>
          </div>
          <div class="flex gap-3">
            <button
              class="rounded border border-outline bg-surface-container px-4 py-2 text-sm font-bold text-on-surface transition-colors hover:border-primary"
              type="button"
              @click="events.refreshEventFolder()"
            >
              Refresh Folder
            </button>
            <button
              class="rounded bg-primary px-4 py-2 text-sm font-bold text-white shadow-[0_4px_12px_rgba(0,112,255,0.3)] transition-transform hover:scale-[1.02]"
              type="button"
              @click="events.downloadMissingTracks()"
            >
              Download
            </button>
          </div>
        </div>

        <div class="mb-6 rounded-xl border border-outline-variant bg-surface-container-high p-5">
          <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div class="flex items-center gap-3">
              <RefreshCw class="text-secondary" :size="20" aria-hidden="true" />
              <div>
                <h3 class="font-bold text-on-surface">Provider Status</h3>
                <p class="mt-1 text-xs text-on-surface-variant">
                  {{ system.deemixStatus?.detail ?? "Provider status not loaded." }}
                </p>
              </div>
            </div>
            <StatusBadge :tone="system.deemixStatus?.available && system.deemixStatus?.authenticated ? 'ok' : 'warn'">
              {{ system.deemixStatus?.available && system.deemixStatus?.authenticated ? "Deemix ready" : "Deemix unavailable" }}
            </StatusBadge>
          </div>
        </div>

        <div class="flex flex-col gap-3">
          <div
            v-for="job in events.globalAcquisitionJobs"
            :key="`${job.provider}-${job.spotifyTrackId}`"
            class="group relative overflow-hidden rounded-lg border border-outline-variant bg-surface-container-high p-4 transition-colors hover:border-primary"
          >
            <div
              v-if="job.status === 'downloading'"
              class="absolute left-0 top-0 h-full w-1/2 bg-primary/5"
            />
            <div class="relative z-10 flex flex-col gap-4 md:flex-row md:items-center">
              <div class="grid h-16 w-16 shrink-0 place-items-center rounded border border-outline-variant bg-surface">
                <FileAudio
                  :class="jobTone(job) === 'ok' ? 'text-secondary' : 'text-on-surface-variant'"
                  :size="24"
                  aria-hidden="true"
                />
              </div>
              <div class="min-w-0 flex-1">
                <div class="mb-2 flex items-start justify-between gap-4">
                  <div class="min-w-0">
                    <h3 class="truncate font-bold text-on-surface">
                      {{ acquisitionTrackTitle(job) }}
                    </h3>
                    <p class="mt-1 truncate text-sm text-on-surface-variant">
                      {{ acquisitionDetail(job) }}
                    </p>
                    <p class="mt-1 text-[10px] font-bold uppercase text-on-surface-variant">
                      {{ job.scope }} - {{ job.sourceName }}
                    </p>
                  </div>
                  <StatusBadge :tone="jobTone(job)">{{ job.status.replace("acquisition_", "") }}</StatusBadge>
                </div>
                <div class="h-1.5 overflow-hidden rounded-full bg-surface-container">
                  <div
                    class="h-full rounded-full"
                    :class="jobTone(job) === 'ok' ? 'w-full bg-secondary' : jobTone(job) === 'warn' ? 'w-2/3 bg-tertiary' : 'w-1/2 bg-primary'"
                  />
                </div>
              </div>
            </div>
          </div>

          <div
            v-if="events.globalAcquisitionJobs.length === 0"
            class="rounded-lg border border-dashed border-outline bg-surface-container p-8 text-center text-sm text-on-surface-variant"
          >
            No acquisition jobs.
          </div>
        </div>
      </section>

      <aside class="w-full shrink-0 lg:w-96">
        <section class="mb-6 rounded-xl border border-outline-variant bg-surface-container-high p-5">
          <div class="mb-4 flex items-center gap-2">
            <Clock class="text-primary" :size="18" aria-hidden="true" />
            <h3 class="font-bold text-on-surface">Event Context</h3>
          </div>
          <div class="grid gap-2">
            <button
              v-for="event in events.summaries"
              :key="event.id"
              class="rounded border p-3 text-left transition-colors"
              :class="
                events.activeEvent?.id === event.id
                  ? 'border-primary bg-primary/5'
                  : 'border-outline-variant bg-surface-container hover:border-primary'
              "
              type="button"
              @click="openEventInEvents(event)"
            >
              <strong class="block truncate text-sm text-on-surface">{{ event.eventName }}</strong>
              <span class="text-xs text-on-surface-variant">
                {{ event.readyTracks }}/{{ event.totalTracks }} ready
              </span>
            </button>
          </div>
        </section>

        <section class="mb-6 rounded-xl border border-outline-variant bg-surface-container-high p-5">
          <div class="mb-4 flex items-center gap-2">
            <AlertTriangle class="text-tertiary" :size="18" aria-hidden="true" />
            <h3 class="font-bold text-on-surface">Metadata Conflicts</h3>
          </div>
          <div class="space-y-3">
            <div
              v-for="track in conflictTracks"
              :key="track.spotifyTrackId"
              class="rounded border border-tertiary/30 bg-tertiary/5 p-3"
            >
              <strong class="block truncate text-sm text-on-surface">{{ track.title }}</strong>
              <span class="block truncate text-xs text-on-surface-variant">
                {{ track.artists.join(", ") }}
              </span>
              <button
                v-if="track.rekordboxContentId"
                class="mt-3 inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="events.acceptSuggestedMatch(track)"
              >
                <CheckCircle2 :size="15" aria-hidden="true" />
                Accept Match
              </button>
            </div>
            <div
              v-for="track in libraryConflictTracks"
              :key="track.spotifyTrackId"
              class="rounded border border-tertiary/30 bg-tertiary/5 p-3"
            >
              <strong class="block truncate text-sm text-on-surface">{{ track.title }}</strong>
              <span class="block truncate text-xs text-on-surface-variant">
                {{ track.artists.join(", ") }} - {{ library.activeReview?.source.spotifyPlaylistName }}
              </span>
              <button
                class="mt-3 inline-flex items-center gap-2 rounded border border-outline bg-surface px-3 py-1.5 text-xs font-bold text-on-surface transition-colors hover:border-primary"
                type="button"
                @click="ui.navigateTo('library')"
              >
                <CheckCircle2 :size="15" aria-hidden="true" />
                Open Library
              </button>
            </div>
            <div v-if="conflictTracks.length === 0 && libraryConflictTracks.length === 0" class="flex items-center gap-2 text-sm text-on-surface-variant">
              <Search :size="16" aria-hidden="true" />
              No metadata conflicts in the selected context.
            </div>
          </div>
        </section>

        <section class="rounded-xl border border-outline-variant bg-surface-container-high p-5">
          <div class="mb-4 flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <AlertTriangle class="text-tertiary" :size="18" aria-hidden="true" />
              <h3 class="font-bold text-on-surface">Sync Proposals</h3>
            </div>
            <span v-if="pendingProposals.length > 0" class="text-xs text-on-surface-variant">
              {{ pendingProposals.length }} pending
            </span>
          </div>
          <div class="space-y-3">
            <div
              v-for="proposal in pendingProposals.slice(0, 8)"
              :key="proposal.id"
              class="rounded border bg-surface-container p-3"
              :class="proposal.proposalType === 'remove_from_rekordbox' ? 'border-error/30' : 'border-outline-variant'"
            >
              <div class="mb-2 flex items-start justify-between gap-2">
                <StatusBadge :tone="proposal.proposalType === 'remove_from_rekordbox' ? 'error' : 'muted'">
                  {{ proposalLabel(proposal.proposalType) }}
                </StatusBadge>
              </div>

              <strong class="block truncate text-sm text-on-surface">
                {{ (proposal.payload as any).title || "Unknown track" }}
              </strong>
              <span class="block truncate text-xs text-on-surface-variant">
                {{ (proposal.payload as any).artist || (proposal.payload as any).artists?.join(", ") || "" }}
              </span>
              <span
                v-if="proposal.filePath"
                class="mt-1 block truncate text-[10px] text-on-surface-variant"
                :title="proposal.filePath"
              >
                {{ proposal.filePath.split("/").slice(-2).join("/") }}
              </span>

              <p class="mt-2 text-[11px] italic text-on-surface-variant">{{ proposal.reason }}</p>

              <div class="mt-3 flex flex-wrap gap-2">
                <button
                  class="rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-primary"
                  type="button"
                  @click="proposals.resolve(proposal.id, 'ignored')"
                >
                  Ignore
                </button>
                <button
                  v-if="proposal.proposalType === 'remove_from_rekordbox'"
                  class="rounded border border-error/40 bg-error/10 px-2.5 py-1 text-[11px] font-bold text-error transition-colors hover:border-error"
                  type="button"
                  @click="proposals.resolve(proposal.id, 'approved')"
                >
                  Remove from Rekordbox
                </button>
                <button
                  class="rounded border border-outline bg-surface px-2.5 py-1 text-[11px] font-bold text-on-surface transition-colors hover:border-secondary"
                  type="button"
                  @click="proposals.resolve(proposal.id, 'protected')"
                >
                  Protect
                </button>
              </div>
            </div>
            <div v-if="pendingProposals.length === 0" class="flex items-center gap-2 text-sm text-on-surface-variant">
              <CheckCircle2 :size="15" aria-hidden="true" />
              No pending proposals.
            </div>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>
