import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { HistoryEvent, LaneQueueStatus } from "@/types/lanes";

type Load = "idle" | "loading" | "loaded" | "error";

interface LanesStore {
  status: LaneQueueStatus | null;
  history: HistoryEvent[];
  loadState: Load;
  error: string | null;
  /** subject_id currently being mutated (pause/resume/overnight), for disabling. */
  busy: number | null;

  fetchLanes: () => Promise<void>;
  fetchHistory: () => Promise<void>;
  pauseLane: (subjectId: number) => Promise<void>;
  resumeLane: (subjectId: number) => Promise<void>;
  setOvernight: (subjectId: number, enabled: boolean) => Promise<void>;
}

export const useLanesStore = create<LanesStore>((set, get) => ({
  status: null,
  history: [],
  loadState: "idle",
  error: null,
  busy: null,

  fetchLanes: async () => {
    if (get().status === null) set({ loadState: "loading" });
    try {
      const status = await api.get<LaneQueueStatus>("/queue/lanes");
      set({ status, loadState: "loaded", error: null });
    } catch (err) {
      set({
        loadState: "error",
        error: err instanceof ApiError ? err.message : "Failed to load lanes.",
      });
    }
  },

  fetchHistory: async () => {
    try {
      const history = await api.get<HistoryEvent[]>("/queue/history?limit=200");
      set({ history });
    } catch {
      // History is non-critical; leave the last known list in place.
    }
  },

  pauseLane: async (subjectId) => {
    await mutate(set, get, subjectId, `/queue/lanes/${subjectId}/pause`);
  },
  resumeLane: async (subjectId) => {
    await mutate(set, get, subjectId, `/queue/lanes/${subjectId}/resume`);
  },
  setOvernight: async (subjectId, enabled) => {
    await mutate(set, get, subjectId, `/queue/lanes/${subjectId}/overnight`, { enabled });
  },
}));

async function mutate(
  set: (partial: Partial<LanesStore>) => void,
  get: () => LanesStore,
  subjectId: number,
  path: string,
  body?: unknown,
): Promise<void> {
  set({ busy: subjectId });
  try {
    await api.post(path, body);
    await get().fetchLanes();
  } finally {
    set({ busy: null });
  }
}
