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

  const toasts = ref<Toast[]>([]);
  let nextToastId = 1;

  const pageTitle = computed(() => {
    if (activeView.value === "dashboard") return "Dashboard";
    if (activeView.value === "library") return "My Library";
    if (activeView.value === "events") return "Events";
    if (activeView.value === "downloadCenter") return "Download & Match Center";
    if (activeView.value === "duplicates") return "Duplicates";
    if (activeView.value === "missing") return "Missing Files";
    if (activeView.value === "untagged") return "Untagged Tracks";
    if (activeView.value === "doctor") return "Doctor";
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

  function setMessage(kind: "success" | "error", message: string): void {
    pushToast(kind, message);
  }

  // Single error-surfacing core: run a task, turn any throw into an error toast,
  // and always run the optional busy-cleanup in `finally`. withLoading,
  // withLoadingFlag and the useApiAction composable all delegate here so the
  // try/catch/toast contract has exactly one implementation.
  type Cleanup = () => void;
  async function withErrorToast<T>(
    task: () => Promise<T>,
    busy?: () => Cleanup
  ): Promise<T | undefined> {
    const cleanup = busy?.();
    try {
      return await task();
    } catch (error) {
      setMessage("error", error instanceof Error ? error.message : String(error));
      return undefined;
    } finally {
      cleanup?.();
    }
  }

  async function withLoading<T>(task: () => Promise<T>): Promise<T | undefined> {
    return withLoadingFlag(loading, task);
  }

  // Same contract as withLoading, but toggles a caller-provided flag
  // (e.g. a panel-local `deezerSearchLoading`) instead of the global one.
  async function withLoadingFlag<T>(
    flag: Ref<boolean>,
    task: () => Promise<T>
  ): Promise<T | undefined> {
    return withErrorToast(task, () => {
      flag.value = true;
      return () => {
        flag.value = false;
      };
    });
  }

  return {
    activeView,
    loading,
    toasts,
    pageTitle,
    navigateTo,
    setMessage,
    pushToast,
    dismissToast,
    withErrorToast,
    withLoading,
    withLoadingFlag,
  };
});
