import { defineStore } from "pinia";
import { ref } from "vue";
import { type ApiClient, type DeemixStatus, type HealthResponse, type RekordboxStatus, createApiClient } from "../lib/api";

export const useSystemStore = defineStore("system", () => {
  const api = ref<ApiClient | null>(null);
  const health = ref<HealthResponse | null>(null);
  const rekordboxStatus = ref<RekordboxStatus | null>(null);
  const deemixStatus = ref<DeemixStatus | null>(null);

  async function init(): Promise<void> {
    api.value = await createApiClient();
  }

  async function refreshStatus(): Promise<void> {
    if (!api.value) return;
    const [nextHealth, nextStatus, nextDeemix] = await Promise.all([
      api.value.getHealth(),
      api.value.getRekordboxStatus(),
      api.value.getDeemixStatus().catch(() => deemixStatus.value),
    ]);
    health.value = nextHealth;
    rekordboxStatus.value = nextStatus;
    deemixStatus.value = nextDeemix;
  }

  return { api, health, rekordboxStatus, deemixStatus, init, refreshStatus };
});
