import { ref } from 'vue'

// ONE shared element so a single 30 s Deezer preview plays app-wide
const playingId = ref<string | number | null>(null)
let audio: HTMLAudioElement | null = null

function ensureAudio(): HTMLAudioElement {
  if (!audio) {
    audio = new Audio()
    audio.addEventListener('ended', () => {
      playingId.value = null
    })
    audio.addEventListener('error', () => {
      playingId.value = null
    })
  }
  return audio
}

export function useAudioPreview() {
  function toggle(id: string | number, url: string) {
    const element = ensureAudio()
    if (playingId.value === id) {
      element.pause()
      playingId.value = null
      return
    }
    element.src = url
    void element
      .play()
      .then(() => {
        playingId.value = id
      })
      .catch(() => {
        playingId.value = null
      })
  }

  function stop() {
    audio?.pause()
    playingId.value = null
  }

  return { playingId, toggle, stop }
}
