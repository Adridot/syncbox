import { defineStore } from "pinia";
import { ref } from "vue";
import {
  type ApiClient,
  type DeemixStatus,
  type HealthResponse,
  type RekordboxCollectionStats,
  type RekordboxStatus,
  type SpotifyConnectionStatus,
  createApiClient,
} from "../lib/api";

export const useSystemStore = defineStore("system", () => {
  const api = ref<ApiClient | null>(null);
  const health = ref<HealthResponse | null>(null);
  const rekordboxStatus = ref<RekordboxStatus | null>(null);
  const deemixStatus = ref<DeemixStatus | null>(null);
  const spotifyStatus = ref<SpotifyConnectionStatus | null>(null);
  const collectionStats = ref<RekordboxCollectionStats | null>(null);

  async function init(): Promise<void> {
    api.value = await createApiClient();
  }

  // Reading the Rekordbox collection is comparatively heavy, so it is loaded
  // on demand (e.g. by the Dashboard) rather than with the lightweight status.
  async function refreshCollectionStats(): Promise<void> {
    if (!api.value) return;
    try {
      collectionStats.value = await api.value.getRekordboxCollectionStats();
    } catch {
      collectionStats.value = { available: false, total: 0, tagged: 0, untagged: 0, withoutIsrc: 0, withoutArtist: 0 };
    }
  }

  async function refreshSpotifyStatus(): Promise<void> {
    if (!api.value) return;
    try {
      spotifyStatus.value = await api.value.getSpotifyStatus();
    } catch {
      // Leave the previous value in place on a transient failure.
    }
  }

  return {
    api,
    health,
    rekordboxStatus,
    deemixStatus,
    spotifyStatus,
    collectionStats,
    init,
    refreshSpotifyStatus,
    refreshCollectionStats,
  };
});
