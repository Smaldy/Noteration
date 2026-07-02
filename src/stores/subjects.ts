import { create } from "zustand";

import { api } from "@/lib/api";
import type { Subject, SubjectCreate } from "@/types/subject";

interface SubjectsStore {
  subjects: Subject[];
  loaded: boolean;
  /** Fetch the subject list (for the upload picker). */
  fetchSubjects: () => Promise<void>;
  /** Create a subject and prepend it to the local list; returns the new row. */
  createSubject: (input: SubjectCreate) => Promise<Subject>;
  /** Delete a subject (and its whole hierarchy, if any) and drop it locally. */
  deleteSubject: (subjectId: number) => Promise<void>;
  /** Bookmark/unbookmark a subject (optimistic; reverts on failure). */
  toggleBookmark: (subjectId: number, bookmarked: boolean) => Promise<void>;
}

export const useSubjectsStore = create<SubjectsStore>((set) => ({
  subjects: [],
  loaded: false,
  fetchSubjects: async () => {
    const subjects = await api.get<Subject[]>("/subjects");
    set({ subjects, loaded: true });
  },
  createSubject: async (input) => {
    const subject = await api.post<Subject>("/subjects", input);
    set((state) => ({ subjects: [...state.subjects, subject] }));
    return subject;
  },
  deleteSubject: async (subjectId) => {
    await api.del(`/subjects/${subjectId}`);
    set((state) => ({
      subjects: state.subjects.filter((s) => s.id !== subjectId),
    }));
  },
  toggleBookmark: async (subjectId, bookmarked) => {
    const apply = (value: boolean) =>
      set((state) => ({
        subjects: state.subjects.map((s) =>
          s.id === subjectId ? { ...s, bookmarked: value } : s,
        ),
      }));
    apply(bookmarked); // optimistic
    try {
      await api.put(`/subjects/${subjectId}/bookmark`, { bookmarked });
    } catch (err) {
      apply(!bookmarked); // revert
      throw err;
    }
  },
}));
