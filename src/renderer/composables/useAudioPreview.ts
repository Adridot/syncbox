import { onUnmounted, ref } from "vue";

/**
 * Single-instance audio preview. Only one clip plays at a time across the app
 * because we lazily create one shared <audio> element. Returns the currently
 * playing id (caller-defined, e.g. a Deezer track id) and toggle/stop helpers.
 */
let sharedAudio: HTMLAudioElement | null = null;

function getAudio(): HTMLAudioElement | null {
  if (typeof window === "undefined") return null;
  if (!sharedAudio) {
    sharedAudio = new Audio();
  }
  return sharedAudio;
}

export function useAudioPreview() {
  const playingId = ref<string | null>(null);

  const audio = getAudio();
  const onEnded = () => {
    playingId.value = null;
  };
  audio?.addEventListener("ended", onEnded);

  function toggle(id: string, url: string | null | undefined): void {
    if (!audio || !url) return;
    if (playingId.value === id) {
      audio.pause();
      playingId.value = null;
      return;
    }
    audio.src = url;
    audio
      .play()
      .then(() => {
        playingId.value = id;
      })
      .catch(() => {
        playingId.value = null;
      });
  }

  function stop(): void {
    if (audio) {
      audio.pause();
      audio.currentTime = 0;
    }
    playingId.value = null;
  }

  onUnmounted(() => {
    audio?.removeEventListener("ended", onEnded);
    stop();
  });

  return { playingId, toggle, stop };
}
