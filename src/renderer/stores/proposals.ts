import { defineStore } from "pinia";
import { ref } from "vue";
import type { SyncProposal } from "../lib/api";
import { useSystemStore } from "./system";
import { useUiStore } from "./ui";

export const useProposalsStore = defineStore("proposals", () => {
  const proposals = ref<SyncProposal[]>([]);

  async function refresh(): Promise<void> {
    const system = useSystemStore();
    if (!system.api) return;
    proposals.value = await system.api.listProposals();
  }

  async function resolve(proposalId: number, status: string): Promise<void> {
    const system = useSystemStore();
    const ui = useUiStore();
    if (!system.api) return;
    await ui.withLoading(async () => {
      await system.api!.resolveProposal(proposalId, status);
      proposals.value = await system.api!.listProposals();
      ui.setMessage("success", "Sync proposal updated.");
    });
  }

  return { proposals, refresh, resolve };
});
