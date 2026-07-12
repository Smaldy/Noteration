import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { BatchUploadResult, UploadResult } from "@/types/document";
import type { DocumentMode, DocumentSummary } from "@/types/library";

type LoadState = "idle" | "loading" | "loaded" | "error";

export interface LibraryStore {
  documents: DocumentSummary[];
  status: LoadState;
  error: string | null;
  /** Fetch this section's documents from `GET /api/documents?mode=…` (newest first). */
  fetchDocuments: () => Promise<void>;
  /** Upload a PDF to a subject in this section's mode, then refresh the list.
   * ``onProgress`` reports file-transfer percentage (0–100) during the upload. */
  uploadDocument: (
    subjectId: number,
    file: File,
    onProgress?: (pct: number) => void,
  ) => Promise<UploadResult>;
  /** Upload many PDFs for unattended overnight generation, then refresh. */
  batchUploadOvernight: (
    subjectId: number,
    files: File[],
    onProgress?: (pct: number) => void,
  ) => Promise<BatchUploadResult>;
  /** Delete a subject (and all its documents/topics), then refresh the list. */
  deleteSubject: (subjectId: number) => Promise<void>;
  /** Delete one document (its subject and sibling documents stay), then refresh. */
  deleteDocument: (documentId: number) => Promise<void>;
  /** Bookmark/unbookmark a subject (optimistic; reverts on failure). */
  toggleSubjectBookmark: (subjectId: number, bookmarked: boolean) => Promise<void>;
  /** Persist a new manual order of the cards (optimistic). */
  reorderDocuments: (orderedIds: number[]) => Promise<void>;
  /** Re-queue a failed/rate-limited audio document for transcription. */
  retryTranscription: (documentId: number) => Promise<void>;
}

// One store per section (study = Library, exam = Exam Prep). The two never share
// state, so the same DocumentCard/UploadDialog work in both via an injected store.
function createDocumentsStore(mode: DocumentMode) {
  const failMessage =
    mode === "exam"
      ? "Failed to load your exam prep."
      : "Failed to load your library.";
  // True while a drag-reorder is mid-persist, so a background poll landing in the
  // window between the optimistic update and the PUT can't overwrite the new order.
  let reordering = false;
  return create<LibraryStore>((set, get) => ({
    documents: [],
    status: "idle",
    error: null,
    fetchDocuments: async () => {
      // Only show the spinner on the first load; background polls (in-flight
      // transcription/generation) refresh silently rather than flashing "loading".
      const first = get().documents.length === 0;
      if (first) set({ status: "loading", error: null });
      try {
        const documents = await api.get<DocumentSummary[]>(
          `/documents?mode=${mode}`,
        );
        if (reordering) return; // don't clobber an optimistic reorder mid-persist
        set({ documents, status: "loaded" });
      } catch (err) {
        // A failed background poll keeps the last good list; only surface errors
        // when we have nothing to show.
        if (first) {
          const error = err instanceof ApiError ? err.message : failMessage;
          set({ status: "error", error });
        }
      }
    },
    uploadDocument: async (subjectId, file, onProgress) => {
      const form = new FormData();
      form.append("subject_id", String(subjectId));
      form.append("file", file);
      form.append("mode", mode);
      const result = await api.uploadWithProgress<UploadResult>(
        "/documents",
        form,
        onProgress,
      );
      await get().fetchDocuments();
      return result;
    },
    batchUploadOvernight: async (subjectId, files, onProgress) => {
      const form = new FormData();
      form.append("subject_id", String(subjectId));
      for (const file of files) form.append("files", file);
      const result = await api.uploadWithProgress<BatchUploadResult>(
        "/documents/batch",
        form,
        onProgress,
      );
      await get().fetchDocuments();
      return result;
    },
  deleteSubject: async (subjectId) => {
    await api.del(`/subjects/${subjectId}`);
    await get().fetchDocuments();
  },
  deleteDocument: async (documentId) => {
    await api.del(`/documents/${documentId}`);
    await get().fetchDocuments();
  },
  toggleSubjectBookmark: async (subjectId, bookmarked) => {
    const apply = (value: boolean) =>
      set((state) => ({
        documents: state.documents.map((d) =>
          d.subject_id === subjectId ? { ...d, subject_bookmarked: value } : d,
        ),
      }));
    apply(bookmarked); // optimistic
    try {
      await api.put(`/subjects/${subjectId}/bookmark`, { bookmarked });
    } catch {
      apply(!bookmarked); // revert
    }
  },
  reorderDocuments: async (orderedIds) => {
    const previous = get().documents;
    const byId = new Map(previous.map((d) => [d.id, d]));
    const next = orderedIds
      .map((id) => byId.get(id))
      .filter((d): d is DocumentSummary => d !== undefined);
    reordering = true;
    set({ documents: next }); // optimistic
    try {
      await api.put("/documents/reorder", { ids: orderedIds });
    } catch {
      set({ documents: previous }); // revert
    } finally {
      reordering = false;
    }
  },
  retryTranscription: async (documentId) => {
    // Optimistically flip the card back to transcribing; refresh for truth.
    set((state) => ({
      documents: state.documents.map((d) =>
        d.id === documentId
          ? { ...d, status: "transcribing", status_detail: null }
          : d,
      ),
    }));
    await api.post(`/documents/${documentId}/transcribe/retry`, {});
    await get().fetchDocuments();
  },
  }));
}

/** Full-study documents (the Library home screen). */
export const useLibraryStore = createDocumentsStore("study");
/** Assessment-only documents (the Exam Prep section). */
export const useExamStore = createDocumentsStore("exam");
