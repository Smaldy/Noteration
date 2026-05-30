import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { QueueStatus } from "@/types/queue";

type Load = "idle" | "loading" | "loaded" | "error";

interface QueueStore {
  status: QueueStatus | null;
  loadState: Load;
  error: string | null;
  retrying: number | null;
  /** Fetch queue status, optionally scoped to a document. */
  fetchStatus: (documentId?: number) => Promise<void>;
  /** Requeue a topic's failed jobs, then refresh. */
  retryTopic: (topicId: number, documentId?: number) => Promise<void>;
}

function path(documentId?: number): string {
  return documentId === undefined
    ? "/queue/status"
    : `/queue/status?document_id=${documentId}`;
}

export const useQueueStore = create<QueueStore>((set, get) => ({
  status: null,
  loadState: "idle",
  error: null,
  retrying: null,

  fetchStatus: async (documentId) => {
    // Don't flash the spinner on background polls once we have data.
    if (get().status === null) set({ loadState: "loading" });
    try {
      const status = await api.get<QueueStatus>(path(documentId));
      set({ status, loadState: "loaded", error: null });
    } catch (err) {
      set({
        loadState: "error",
        error:
          err instanceof ApiError ? err.message : "Failed to load the queue.",
      });
    }
  },

  retryTopic: async (topicId, documentId) => {
    set({ retrying: topicId });
    try {
      await api.post(`/queue/topics/${topicId}/retry`);
      await get().fetchStatus(documentId);
    } finally {
      set({ retrying: null });
    }
  },
}));
