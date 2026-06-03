import { defineStore } from "pinia";
import { computed, ref } from "vue";
import type { RekordboxTag, SpotifyPlaylistSummary } from "../lib/api";
import { useSystemStore } from "./system";

export const useSpotifyStore = defineStore("spotify", () => {
  const playlists = ref<SpotifyPlaylistSummary[]>([]);
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
    while (true) {
      const page = await system.api.listSpotifyPlaylists(offset);
      items.push(...page.items);
      if (page.nextOffset == null || page.items.length === 0) break;
      offset = page.nextOffset;
    }
    playlists.value = items;
  }

  async function refreshRekordboxTags(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    rekordboxTags.value = await system.api.listRekordboxTags().catch(() => rekordboxTags.value);
  }

  return { playlists, rekordboxTags, availableTagNames, fetchAllPlaylists, refreshRekordboxTags };
});
