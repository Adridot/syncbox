import { defineStore } from "pinia";
import { ref, computed } from "vue";
import type { ViewKey } from "../types/ui";

export const useUiStore = defineStore("ui", () => {
  const activeView = ref<ViewKey>("dashboard");
  const loading = ref(false);
  const errorMessage = ref("");
  const successMessage = ref("");
  const searchQuery = ref("");

  const pageTitle = computed(() => {
    if (activeView.value === "dashboard") return "Dashboard";
    if (activeView.value === "library") return "My Library";
    if (activeView.value === "events") return "Event Imports";
    if (activeView.value === "manualEvents") return "Manual Event";
    if (activeView.value === "downloadCenter") return "Download & Match Center";
    return "Settings";
  });

  function navigateTo(view: ViewKey): void {
    activeView.value = view;
  }

  function setMessage(kind: "success" | "error", message: string): void {
    successMessage.value = kind === "success" ? message : "";
    errorMessage.value = kind === "error" ? message : "";
  }

  function clearMessages(): void {
    errorMessage.value = "";
    successMessage.value = "";
  }

  async function withLoading<T>(task: () => Promise<T>): Promise<T | undefined> {
    loading.value = true;
    clearMessages();
    try {
      return await task();
    } catch (error) {
      setMessage("error", error instanceof Error ? error.message : String(error));
      return undefined;
    } finally {
      loading.value = false;
    }
  }

  return {
    activeView,
    loading,
    errorMessage,
    successMessage,
    searchQuery,
    pageTitle,
    navigateTo,
    setMessage,
    clearMessages,
    withLoading,
  };
});
