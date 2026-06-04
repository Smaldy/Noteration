import { create } from "zustand";

import { api } from "@/lib/api";
import type { ChapterQueueState, ChapterStatus } from "@/types/chapter";

interface ChaptersState {
  documentId: number | null;
  statuses: ChapterStatus[];
  busy: number | null; // chapter id mid pause/resume
  error: string | null;
  /** Fetch (or refresh) the per-chapter status for a document. */
  fetch: (documentId: number) => Promise<void>;
  /** PATCH a chapter lane, then refresh this document's statuses. */
  setQueueState: (chapterId: number, state: ChapterQueueState) => Promise<void>;
}

export const useChaptersStore = create<ChaptersState>((set, get) => ({
  documentId: null,
  statuses: [],
  busy: null,
  error: null,

  fetch: async (documentId) => {
    try {
      const statuses = await api.get<ChapterStatus[]>(
        `/documents/${documentId}/chapters/status`,
      );
      set({ statuses, documentId, error: null });
    } catch {
      set({ error: "Could not load chapter status." });
    }
  },

  setQueueState: async (chapterId, state) => {
    set({ busy: chapterId });
    try {
      await api.patch(`/chapters/${chapterId}/queue_state`, { queue_state: state });
      const documentId = get().documentId;
      if (documentId != null) {
        const statuses = await api.get<ChapterStatus[]>(
          `/documents/${documentId}/chapters/status`,
        );
        set({ statuses });
      }
    } finally {
      set({ busy: null });
    }
  },
}));
