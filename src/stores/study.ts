import { create } from "zustand";

import { ApiError, api } from "@/lib/api";
import type { DocumentTree, Note, TopicContent } from "@/types/study";

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
  /** Lazily transcribe the topic's pending formulas, then refresh its content. */
  transcribeFormulas: (topicId: number) => Promise<void>;
  /** Generate more MCQs or flashcards for a topic, then refresh its content. */
  generateMore: (topicId: number, kind: "mcqs" | "flashcards") => Promise<void>;
  /** Save an edited note's markdown (and optionally its lock), updating in place. */
  saveNote: (noteId: number, content_md: string, locked?: boolean) => Promise<void>;
  /** Add a manual note block under the open topic. */
  addNote: (topicId: number, content_md?: string) => Promise<void>;
  /** Delete a note block from the open topic. */
  removeNote: (noteId: number) => Promise<void>;
  /** Delete a topic (and its content), then refresh the document's tree. */
  deleteTopic: (topicId: number, documentId: number) => Promise<void>;
  /** Bookmark/unbookmark a topic (optimistic across tree + open content). */
  toggleTopicBookmark: (topicId: number, bookmarked: boolean) => Promise<void>;
  /** Persist a chapter's new topic order (optimistic). */
  reorderTopics: (chapterId: number, orderedIds: number[]) => Promise<void>;
  /** Clear the selected topic's content (e.g. when none is selected). */
  clearContent: () => void;
}

export const useStudyStore = create<StudyStore>((set, get) => ({
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

  transcribeFormulas: async (topicId) => {
    // The endpoint returns the refreshed topic content (formulas flipped to
    // reconstructed). Only update if this topic is still the open one.
    const content = await api.post<TopicContent>(
      `/topics/${topicId}/formulas/transcribe`,
      {},
    );
    set((state) =>
      state.content && state.content.id === topicId
        ? { content, contentStatus: "loaded" }
        : state,
    );
  },

  generateMore: async (topicId, kind) => {
    // Returns the refreshed topic content with the newly appended items. Only
    // apply if this topic is still the open one. Errors propagate to the caller
    // (the tab shows them) — e.g. 503 when no provider has headroom.
    const content = await api.post<TopicContent>(`/topics/${topicId}/generate`, {
      kind,
    });
    set((state) =>
      state.content && state.content.id === topicId
        ? { content, contentStatus: "loaded" }
        : state,
    );
  },

  saveNote: async (noteId, content_md, locked) => {
    const updated = await api.patch<Note>(`/notes/${noteId}`, {
      content_md,
      ...(locked === undefined ? {} : { locked }),
    });
    set((state) =>
      state.content
        ? {
            content: {
              ...state.content,
              notes: state.content.notes.map((n) =>
                n.id === noteId ? updated : n,
              ),
            },
          }
        : state,
    );
  },

  addNote: async (topicId, content_md = "") => {
    const created = await api.post<Note>("/notes", { topic_id: topicId, content_md });
    set((state) =>
      state.content && state.content.id === topicId
        ? { content: { ...state.content, notes: [...state.content.notes, created] } }
        : state,
    );
  },

  removeNote: async (noteId) => {
    await api.del(`/notes/${noteId}`);
    set((state) =>
      state.content
        ? {
            content: {
              ...state.content,
              notes: state.content.notes.filter((n) => n.id !== noteId),
            },
          }
        : state,
    );
  },

  deleteTopic: async (topicId, documentId) => {
    await api.del(`/topics/${topicId}`);
    await get().fetchTree(documentId);
  },

  toggleTopicBookmark: async (topicId, bookmarked) => {
    const apply = (value: boolean) =>
      set((state) => ({
        tree: state.tree
          ? {
              ...state.tree,
              chapters: state.tree.chapters.map((ch) => ({
                ...ch,
                topics: ch.topics.map((t) =>
                  t.id === topicId ? { ...t, bookmarked: value } : t,
                ),
              })),
            }
          : state.tree,
        content:
          state.content && state.content.id === topicId
            ? { ...state.content, bookmarked: value }
            : state.content,
      }));
    apply(bookmarked); // optimistic
    try {
      await api.put(`/topics/${topicId}/bookmark`, { bookmarked });
    } catch {
      apply(!bookmarked); // revert
    }
  },

  reorderTopics: async (chapterId, orderedIds) => {
    const previous = get().tree;
    if (!previous) return;
    const next = {
      ...previous,
      chapters: previous.chapters.map((ch) => {
        if (ch.id !== chapterId) return ch;
        const byId = new Map(ch.topics.map((t) => [t.id, t]));
        const topics = orderedIds
          .map((id) => byId.get(id))
          .filter((t): t is (typeof ch.topics)[number] => t !== undefined);
        return { ...ch, topics };
      }),
    };
    set({ tree: next }); // optimistic
    try {
      await api.put("/topics/reorder", { ids: orderedIds });
    } catch {
      set({ tree: previous }); // revert
    }
  },

  clearContent: () => set({ content: null, contentStatus: "idle", contentError: null }),
}));
