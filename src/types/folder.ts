import type { DocumentSummary } from "@/types/library";

/** Tint name from the fixed pastel family. See lib/tints.ts and index.css. */
export type FolderTint = string;

export interface Folder {
  id: number;
  name: string;
  parent_id: number | null;
  /** When set, the folder auto-mirrors this subject's documents. */
  subject_id: number | null;
  tint: FolderTint;
  /** The one folder per subject that auto-mirrors it and gets new notes. */
  is_main: boolean;
  /** Starred in the Library. The bookmark filter narrows to these. */
  bookmarked: boolean;
  order_index: number;
  created_at: string;
  /** Documents + loose files, auto and manual combined. Drives the empty look. */
  item_count: number;
  child_count: number;
  /** First few document ids for the tray preview; resolved from the library store. */
  preview_ids: number[];
}

export interface FolderGroup {
  id: number;
  folder_id: number;
  name: string;
  tint: FolderTint;
  order_index: number;
}

export interface FolderFile {
  id: number;
  folder_id: number;
  group_id: number | null;
  kind: "pdf" | "image";
  filename: string;
  content_type: string;
  url: string;
  generated_document_id: number | null;
  order_index: number;
}

export interface FolderContents {
  folder: Folder;
  groups: FolderGroup[];
  documents: DocumentSummary[];
  /** Document id → group id, or null when ungrouped. Keys arrive as strings. */
  document_groups: Record<string, number | null>;
  /** Document id → starred *in this folder*. Keys arrive as strings. */
  document_bookmarks: Record<string, boolean>;
  files: FolderFile[];
  children: Folder[];
}

export interface FolderCreate {
  name: string;
  parent_id?: number | null;
  subject_id?: number | null;
  tint?: FolderTint;
  is_main?: boolean;
}

export interface FolderUpdate {
  name?: string;
  tint?: FolderTint;
  subject_id?: number | null;
  parent_id?: number | null;
  clear_subject?: boolean;
  clear_parent?: boolean;
  is_main?: boolean;
}
