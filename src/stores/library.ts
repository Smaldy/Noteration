import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { DocumentSummary } from "@/types/library";

type LoadState = "idle" | "loading" | "loaded" | "error";

interface LibraryStore {
  documents: DocumentSummary[];
  status: LoadState;
  error: string | null;
  /** Fetch the document list from `GET /api/documents` (newest first). */
  fetchDocuments: () => Promise<void>;
}

export const useLibraryStore = create<LibraryStore>((set) => ({
  documents: [],
  status: "idle",
  error: null,
  fetchDocuments: async () => {
    set({ status: "loading", error: null });
    try {
      const documents = await api.get<DocumentSummary[]>("/documents");
      set({ documents, status: "loaded" });
    } catch (err) {
      const error =
        err instanceof ApiError ? err.message : "Failed to load your library.";
      set({ status: "error", error });
    }
  },
}));
