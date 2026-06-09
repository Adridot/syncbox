import { useQuery } from "@tanstack/vue-query";
import { computed, watch } from "vue";
import { useSystemStore } from "../../stores/system";

/**
 * Polls the lightweight system status (health + Rekordbox + Deemix + Spotify)
 * through TanStack Query instead of a hand-rolled setInterval. `refetchInterval`
 * replaces the old 5s useRefreshManager timer, and the global
 * `refetchOnWindowFocus` default replaces its "refresh when the tab becomes
 * visible again" watcher — so this one query subsumes two pieces of the manual
 * refresh manager.
 *
 * The result is mirrored into the existing system store refs so the ~25
 * components that read `system.rekordboxStatus` / `.health` / … stay untouched:
 * during the incremental Pinia→vue-query migration the store is a read facade
 * fed by the query. Call once, high in the tree (App.vue).
 */
export function useSystemStatusQuery() {
  const system = useSystemStore();

  const query = useQuery({
    queryKey: ["system", "status"],
    enabled: computed(() => !!system.api),
    refetchInterval: 5_000,
    queryFn: async () => {
      const api = system.api!;
      const [health, rekordbox, deemix, spotify] = await Promise.all([
        api.getHealth(),
        api.getRekordboxStatus(),
        // Deemix/Spotify are best-effort: keep the last known value on a blip
        // rather than flashing the badges to "offline".
        api.getDeemixStatus().catch(() => system.deemixStatus),
        api.getSpotifyStatus().catch(() => system.spotifyStatus),
      ]);
      return { health, rekordbox, deemix, spotify };
    },
  });

  // Bridge query data -> store refs (same direct-assignment pattern the settings
  // store already uses for system.deemixStatus / system.spotifyStatus).
  watch(
    () => query.data.value,
    (data) => {
      if (!data) return;
      system.health = data.health;
      system.rekordboxStatus = data.rekordbox;
      system.deemixStatus = data.deemix ?? system.deemixStatus;
      system.spotifyStatus = data.spotify ?? system.spotifyStatus;
    },
  );

  return query;
}
