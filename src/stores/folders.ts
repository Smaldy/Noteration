import { create } from "zustand";

import { api, ApiError } from "@/lib/api";
import type {
  Folder,
  FolderContents,
  FolderCreate,
  FolderFile,
  FolderGroup,
  FolderUpdate,
} from "@/types/folder";

type Load = "idle" | "loading" | "loaded" | "error";

interface FoldersStore {
  folders: Folder[];
  status: Load;
  error: string | null;

  /** The folder currently open in the folder view, fully resolved. */
  open: FolderContents | null;
  openStatus: Load;

  fetchFolders: () => Promise<void>;
  createFolder: (input: FolderCreate) => Promise<Folder>;
  updateFolder: (folderId: number, changes: FolderUpdate) => Promise<void>;
  deleteFolder: (folderId: number) => Promise<void>;
  reorderFolders: (ids: number[]) => Promise<void>;

  openFolder: (folderId: number) => Promise<void>;
  clearOpen: () => void;

  createGroup: (folderId: number, name: string, tint?: string) => Promise<FolderGroup>;
  updateGroup: (groupId: number, changes: { name?: string; tint?: string }) => Promise<void>;
  deleteGroup: (groupId: number) => Promise<void>;

  setFolderBookmark: (folderId: number, bookmarked: boolean) => Promise<void>;
  setDocumentBookmark: (folderId: number, documentId: number, bookmarked: boolean) => Promise<void>;

  addDocuments: (folderId: number, documentIds: number[], groupId?: number | null) => Promise<void>;
  setDocumentGroup: (folderId: number, documentId: number, groupId: number | null) => Promise<void>;
  removeDocument: (folderId: number, documentId: number) => Promise<void>;

  uploadFile: (folderId: number, file: File, groupId?: number | null) => Promise<FolderFile>;
  deleteFile: (fileId: number) => Promise<void>;
}

export const useFoldersStore = create<FoldersStore>((set, get) => ({
  folders: [],
  status: "idle",
  error: null,
  open: null,
  openStatus: "idle",

  fetchFolders: async () => {
    set({ status: "loading", error: null });
    try {
      set({ folders: await api.get<Folder[]>("/folders"), status: "loaded" });
    } catch (err) {
      set({
        status: "error",
        error: err instanceof ApiError ? err.message : "Failed to load folders.",
      });
    }
  },

  createFolder: async (input) => {
    const folder = await api.post<Folder>("/folders", input);
    set((state) => ({ folders: [...state.folders, folder] }));
    return folder;
  },

  updateFolder: async (folderId, changes) => {
    const updated = await api.patch<Folder>(`/folders/${folderId}`, changes);
    set((state) => ({
      folders: state.folders.map((f) => (f.id === folderId ? updated : f)),
      // Keep the open view's header in step when it's the folder being edited.
      open:
        state.open?.folder.id === folderId
          ? { ...state.open, folder: updated }
          : state.open,
    }));
    // A changed subject tag changes which documents belong here, and that is
    // computed server-side, so the open folder has to be refetched.
    if (changes.subject_id !== undefined || changes.clear_subject) {
      if (get().open?.folder.id === folderId) await get().openFolder(folderId);
    }
  },

  deleteFolder: async (folderId) => {
    await api.del(`/folders/${folderId}`);
    set((state) => ({
      // Children are cascade-deleted server-side; drop them locally too.
      folders: state.folders.filter(
        (f) => f.id !== folderId && f.parent_id !== folderId,
      ),
      open: state.open?.folder.id === folderId ? null : state.open,
    }));
  },

  reorderFolders: async (ids) => {
    const previous = get().folders;
    const byId = new Map(previous.map((f) => [f.id, f]));
    set({
      folders: ids.map((id, index) => ({ ...byId.get(id)!, order_index: index })),
    });
    try {
      await api.put("/folders/reorder", { ids });
    } catch (err) {
      set({ folders: previous }); // revert
      throw err;
    }
  },

  openFolder: async (folderId) => {
    set({ openStatus: "loading" });
    try {
      const contents = await api.get<FolderContents>(`/folders/${folderId}`);
      set({ open: contents, openStatus: "loaded" });
    } catch (err) {
      set({
        openStatus: "error",
        error: err instanceof ApiError ? err.message : "Failed to open folder.",
      });
    }
  },

  clearOpen: () => set({ open: null, openStatus: "idle" }),

  createGroup: async (folderId, name, tint) => {
    const group = await api.post<FolderGroup>(`/folders/${folderId}/groups`, {
      name,
      tint,
    });
    set((state) =>
      state.open?.folder.id === folderId
        ? { open: { ...state.open, groups: [...state.open.groups, group] } }
        : {},
    );
    return group;
  },

  updateGroup: async (groupId, changes) => {
    const group = await api.patch<FolderGroup>(`/folders/groups/${groupId}`, changes);
    set((state) =>
      state.open
        ? {
            open: {
              ...state.open,
              groups: state.open.groups.map((g) => (g.id === groupId ? group : g)),
            },
          }
        : {},
    );
  },

  deleteGroup: async (groupId) => {
    await api.del(`/folders/groups/${groupId}`);
    // Contents survive the group (SET NULL server-side), so refetch rather than
    // filtering locally — items need to reappear in the ungrouped area.
    const folderId = get().open?.folder.id;
    if (folderId != null) await get().openFolder(folderId);
  },

  setFolderBookmark: async (folderId, bookmarked) => {
    const apply = (value: boolean) =>
      set((state) => ({
        folders: state.folders.map((f) =>
          f.id === folderId ? { ...f, bookmarked: value } : f,
        ),
        open:
          state.open?.folder.id === folderId
            ? { ...state.open, folder: { ...state.open.folder, bookmarked: value } }
            : state.open,
      }));
    apply(bookmarked); // optimistic
    try {
      await api.put(`/folders/${folderId}/bookmark`, { bookmarked });
    } catch (err) {
      apply(!bookmarked); // revert
      throw err;
    }
  },

  setDocumentBookmark: async (folderId, documentId, bookmarked) => {
    const apply = (value: boolean) =>
      set((state) =>
        state.open?.folder.id === folderId
          ? {
              open: {
                ...state.open,
                document_bookmarks: {
                  ...state.open.document_bookmarks,
                  [String(documentId)]: value,
                },
              },
            }
          : {},
      );
    apply(bookmarked); // optimistic
    try {
      await api.put(`/folders/${folderId}/documents/${documentId}/bookmark`, {
        bookmarked,
      });
    } catch (err) {
      apply(!bookmarked); // revert
      throw err;
    }
  },

  addDocuments: async (folderId, documentIds, groupId = null) => {
    await api.post(`/folders/${folderId}/documents`, {
      document_ids: documentIds,
      group_id: groupId,
    });
    if (get().open?.folder.id === folderId) await get().openFolder(folderId);
    await get().fetchFolders(); // item_count moved
  },

  setDocumentGroup: async (folderId, documentId, groupId) => {
    // Optimistic: the card visibly moves band before the round trip lands.
    set((state) =>
      state.open?.folder.id === folderId
        ? {
            open: {
              ...state.open,
              document_groups: {
                ...state.open.document_groups,
                [String(documentId)]: groupId,
              },
            },
          }
        : {},
    );
    try {
      await api.put(`/folders/${folderId}/documents/${documentId}/group`, {
        group_id: groupId,
      });
    } catch (err) {
      if (get().open?.folder.id === folderId) await get().openFolder(folderId);
      throw err;
    }
  },

  removeDocument: async (folderId, documentId) => {
    await api.del(`/folders/${folderId}/documents/${documentId}`);
    // A subject-tagged document stays visible after its manual placement goes,
    // so the server decides what remains.
    if (get().open?.folder.id === folderId) await get().openFolder(folderId);
    await get().fetchFolders();
  },

  uploadFile: async (folderId, file, groupId = null) => {
    const form = new FormData();
    form.append("file", file);
    if (groupId != null) form.append("group_id", String(groupId));
    const stored = await api.upload<FolderFile>(`/folders/${folderId}/files`, form);
    set((state) =>
      state.open?.folder.id === folderId
        ? { open: { ...state.open, files: [...state.open.files, stored] } }
        : {},
    );
    await get().fetchFolders();
    return stored;
  },

  deleteFile: async (fileId) => {
    await api.del(`/folders/files/${fileId}`);
    set((state) =>
      state.open
        ? { open: { ...state.open, files: state.open.files.filter((f) => f.id !== fileId) } }
        : {},
    );
    await get().fetchFolders();
  },
}));
