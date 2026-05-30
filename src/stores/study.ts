import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { DocumentTree, TopicContent } from "@/types/study";

type Load = "idle" | "loading" | "loaded" | "error";

interface StudyStore {
  tree: DocumentTree | null;
  treeStatus: Load;
  treeError: string | null;

  content: TopicContent | null;
  contentStatus: Load;
  contentError: string | null;

  /** Load the sidebar tree for a document. */
  fetchTree: (documentId: number) => Promise<void>;
  /** Load a topic's notes/MCQs/flashcards for the tabs. */
  fetchTopic: (topicId: number) => Promise<void>;
  /** Clear the selected topic's content (e.g. when none is selected). */
  clearContent: () => void;
}

export const useStudyStore = create<StudyStore>((set) => ({
  tree: null,
  treeStatus: "idle",
  treeError: null,
  content: null,
  contentStatus: "idle",
  contentError: null,

  fetchTree: async (documentId) => {
    set({ treeStatus: "loading", treeError: null });
    try {
      const tree = await api.get<DocumentTree>(`/documents/${documentId}/tree`);
      set({ tree, treeStatus: "loaded" });
    } catch (err) {
      set({
        treeStatus: "error",
        treeError:
          err instanceof ApiError ? err.message : "Failed to load the document.",
      });
    }
  },

  fetchTopic: async (topicId) => {
    set({ contentStatus: "loading", contentError: null });
    try {
      const content = await api.get<TopicContent>(`/topics/${topicId}`);
      set({ content, contentStatus: "loaded" });
    } catch (err) {
      set({
        contentStatus: "error",
        contentError:
          err instanceof ApiError ? err.message : "Failed to load the topic.",
      });
    }
  },

  clearContent: () => set({ content: null, contentStatus: "idle", contentError: null }),
}));
