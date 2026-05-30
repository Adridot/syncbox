import { onUnmounted, ref, watch } from "vue";
import type { GlobalAcquisitionJob } from "../lib/api";
import { useEventsStore } from "../stores/events";
import { useSystemStore } from "../stores/system";

/**
 * Subscribes to the server's SSE acquisition stream. While connected, the
 * server drives the refresh loop and pushes job updates, so the polling-based
 * refresh manager can skip its own job polling (see `connected`).
 */
export function useAcquisitionStream() {
  const system = useSystemStore();
  const events = useEventsStore();
  const connected = ref(false);

  let source: EventSource | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

  function close(): void {
    if (reconnectTimer) {
      clearTimeout(reconnectTimer);
      reconnectTimer = null;
    }
    if (source) {
      source.close();
      source = null;
    }
    connected.value = false;
  }

  function connect(): void {
    if (source || !system.api) return;
    let url: string;
    try {
      url = system.api.streamUrl("/api/acquisition/stream");
    } catch {
      return;
    }
    const es = new EventSource(url);
    source = es;

    es.addEventListener("open", () => {
      connected.value = true;
    });

    es.addEventListener("jobs", (event) => {
      try {
        const data = JSON.parse((event as MessageEvent).data) as GlobalAcquisitionJob[];
        events.globalAcquisitionJobs = data;
      } catch {
        /* ignore malformed frame */
      }
    });

    es.addEventListener("error", () => {
      connected.value = false;
      // EventSource auto-reconnects, but if the connection is fully closed
      // (e.g. service restart) we recreate it after a short backoff.
      if (es.readyState === EventSource.CLOSED) {
        close();
        reconnectTimer = setTimeout(connect, 3000);
      }
    });
  }

  // Connect once the API client is available.
  watch(
    () => system.api,
    (api) => {
      if (api) connect();
    },
    { immediate: true }
  );

  onUnmounted(close);

  return { connected };
}
