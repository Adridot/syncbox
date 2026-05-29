import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { RekordboxTag, SpotifyPlaylistSummary, SpotifyPlaylistsResponse } from "../lib/api";
import { useSystemStore } from "./system";

export const useSpotifyStore = defineStore("spotify", () => {
  const playlists = ref<SpotifyPlaylistSummary[]>([]);
  const playlistPage = ref<SpotifyPlaylistsResponse | null>(null);
  const playlistTotal = ref(0);
  const rekordboxTags = ref<RekordboxTag[]>([]);

  const availableTagNames = computed(() =>
    rekordboxTags.value
      .map((tag) => tag.name)
      .filter(Boolean)
      .sort((a, b) => a.localeCompare(b))
  );

  async function fetchAllPlaylists(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    const items: SpotifyPlaylistSummary[] = [];
    let offset = 0;
    let total = 0;
    while (true) {
      const page = await system.api.listSpotifyPlaylists(offset);
      items.push(...page.items);
      total = page.total;
      if (page.nextOffset == null || page.items.length === 0) break;
      offset = page.nextOffset;
    }
    playlists.value = items;
    playlistTotal.value = total;
    playlistPage.value = { items, total, limit: items.length, offset: 0, nextOffset: null };
  }

  async function refreshRekordboxTags(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    rekordboxTags.value = await system.api.listRekordboxTags().catch(() => rekordboxTags.value);
  }

  return { playlists, playlistPage, playlistTotal, rekordboxTags, availableTagNames, fetchAllPlaylists, refreshRekordboxTags };
});
