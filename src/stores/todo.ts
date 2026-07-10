import { create } from "zustand";

import { api } from "@/lib/api";
import type { TodoItem } from "@/types/todo";

interface TodoStore {
  items: TodoItem[];
  loaded: boolean;

  /** Load the list once (the widget is always mounted); `force` refetches. */
  fetch: (force?: boolean) => Promise<void>;
  /** Pin topics to the list (idempotent server-side). */
  add: (topicIds: number[]) => Promise<void>;
  /** Unpin one topic (the hover ✕). Optimistic with revert. */
  remove: (topicId: number) => Promise<void>;
  /** Drop every checked-off item. */
  clearCompleted: () => Promise<void>;
  /** Mirror a studied toggle done elsewhere (Notes tab / widget checkbox) so
   *  the list stays in sync without a refetch. */
  applyStudied: (topicId: number, studied: boolean) => void;
}

export const useTodoStore = create<TodoStore>((set, get) => ({
  items: [],
  loaded: false,

  fetch: async (force = false) => {
    if (get().loaded && !force) return;
    const items = await api.get<TodoItem[]>("/todo");
    set({ items, loaded: true });
  },

  add: async (topicIds) => {
    const items = await api.post<TodoItem[]>("/todo", { topic_ids: topicIds });
    set({ items, loaded: true });
  },

  remove: async (topicId) => {
    const previous = get().items;
    set({ items: previous.filter((i) => i.topic_id !== topicId) });
    try {
      await api.del(`/todo/${topicId}`);
    } catch {
      set({ items: previous });
    }
  },

  clearCompleted: async () => {
    const previous = get().items;
    set({ items: previous.filter((i) => !i.studied) });
    try {
      await api.del("/todo/completed");
    } catch {
      set({ items: previous });
    }
  },

  applyStudied: (topicId, studied) =>
    set((state) => ({
      items: state.items.map((i) =>
        i.topic_id === topicId ? { ...i, studied } : i,
      ),
    })),
}));
