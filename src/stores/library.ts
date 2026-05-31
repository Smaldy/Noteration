import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { UploadResult } from "@/types/document";
import type { DocumentSummary } from "@/types/library";

type LoadState = "idle" | "loading" | "loaded" | "error";

interface LibraryStore {
  documents: DocumentSummary[];
  status: LoadState;
  error: string | null;
  /** Fetch the document list from `GET /api/documents` (newest first). */
  fetchDocuments: () => Promise<void>;
  /** Upload a PDF to a subject, then refresh the list; returns the upload result. */
  uploadDocument: (subjectId: number, file: File) => Promise<UploadResult>;
  /** Delete a subject (and all its documents/topics), then refresh the list. */
  deleteSubject: (subjectId: number) => Promise<void>;
}

export const useLibraryStore = create<LibraryStore>((set, get) => ({
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
  uploadDocument: async (subjectId, file) => {
    const form = new FormData();
    form.append("subject_id", String(subjectId));
    form.append("file", file);
    const result = await api.upload<UploadResult>("/documents", form);
    await get().fetchDocuments();
    return result;
  },
  deleteSubject: async (subjectId) => {
    await api.del(`/subjects/${subjectId}`);
    await get().fetchDocuments();
  },
}));
