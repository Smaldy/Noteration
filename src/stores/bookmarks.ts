import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { Bookmarks } from "@/types/bookmarks";

type Load = "idle" | "loading" | "loaded" | "error";

interface BookmarksStore {
  data: Bookmarks | null;
  status: Load;
  error: string | null;
  fetchBookmarks: () => Promise<void>;
}

export const useBookmarksStore = create<BookmarksStore>((set) => ({
  data: null,
  status: "idle",
  error: null,
  fetchBookmarks: async () => {
    set({ status: "loading", error: null });
    try {
      const data = await api.get<Bookmarks>("/bookmarks");
      set({ data, status: "loaded" });
    } catch (err) {
      set({
        status: "error",
        error: err instanceof ApiError ? err.message : "Failed to load bookmarks.",
      });
    }
  },
}));
