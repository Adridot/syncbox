import { defineStore } from "pinia";
import { ref, computed, type Ref } from "vue";
import type { ViewKey } from "../types/ui";

export type ToastKind = "success" | "error" | "info";

export interface Toast {
  id: number;
  kind: ToastKind;
  message: string;
}

const DEFAULT_TIMEOUTS: Record<ToastKind, number> = {
  success: 4000,
  info: 5000,
  error: 8000,
};

export const useUiStore = defineStore("ui", () => {
  const activeView = ref<ViewKey>("dashboard");
  const loading = ref(false);
  // errorMessage/successMessage are kept for back-compat: several views branch
  // on `if (!ui.errorMessage)` right after an awaited action.
  const errorMessage = ref("");
  const successMessage = ref("");
  const searchQuery = ref("");

  const toasts = ref<Toast[]>([]);
  let nextToastId = 1;

  const pageTitle = computed(() => {
    if (activeView.value === "dashboard") return "Dashboard";
    if (activeView.value === "library") return "My Library";
    if (activeView.value === "events") return "Events";
    if (activeView.value === "downloadCenter") return "Download & Match Center";
    return "Settings";
  });

  function navigateTo(view: ViewKey): void {
    activeView.value = view;
  }

  function dismissToast(id: number): void {
    toasts.value = toasts.value.filter((toast) => toast.id !== id);
  }

  function pushToast(kind: ToastKind, message: string, timeout?: number): number {
    const id = nextToastId++;
    toasts.value = [...toasts.value, { id, kind, message }];
    const ms = timeout ?? DEFAULT_TIMEOUTS[kind];
    if (ms > 0) {
      setTimeout(() => dismissToast(id), ms);
    }
    return id;
  }

  function notify(kind: ToastKind, message: string): void {
    pushToast(kind, message);
  }

  function setMessage(kind: "success" | "error", message: string): void {
    successMessage.value = kind === "success" ? message : "";
    errorMessage.value = kind === "error" ? message : "";
    pushToast(kind, message);
  }

  function clearMessages(): void {
    errorMessage.value = "";
    successMessage.value = "";
  }

  async function withLoading<T>(task: () => Promise<T>): Promise<T | undefined> {
    return withLoadingFlag(loading, task);
  }

  // Same error-surfacing contract as withLoading, but toggles a caller-provided
  // flag (e.g. a panel-local `deezerSearchLoading`) instead of the global one.
  async function withLoadingFlag<T>(
    flag: Ref<boolean>,
    task: () => Promise<T>
  ): Promise<T | undefined> {
    flag.value = true;
    clearMessages();
    try {
      return await task();
    } catch (error) {
      setMessage("error", error instanceof Error ? error.message : String(error));
      return undefined;
    } finally {
      flag.value = false;
    }
  }

  return {
    activeView,
    loading,
    errorMessage,
    successMessage,
    searchQuery,
    toasts,
    pageTitle,
    navigateTo,
    setMessage,
    clearMessages,
    notify,
    pushToast,
    dismissToast,
    withLoading,
    withLoadingFlag,
  };
});
