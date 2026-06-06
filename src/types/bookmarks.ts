/** Mirrors `backend/schemas/bookmarks.py`. */

import type { TopicPriority } from "./structure";
import type { TopicStatus } from "./study";

export interface BookmarkSubject {
  id: number;
  name: string;
  accent_color: string | null;
  /** ISO date (YYYY-MM-DD) or null. */
  exam_date: string | null;
  bookmarked: boolean;
  /** ISO datetime. */
  created_at: string;
  /** Primary document to open; null when the subject has no documents yet. */
  document_id: number | null;
}

export interface BookmarkTopic {
  id: number;
  title: string;
  subject_id: number;
  subject_name: string;
  document_id: number;
  chapter_title: string;
  status: TopicStatus;
  priority: TopicPriority;
}

export interface Bookmarks {
  subjects: BookmarkSubject[];
  topics: BookmarkTopic[];
}
