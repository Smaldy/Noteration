/** Mirrors `backend/schemas/bookmarks.py`. */

import type { TopicPriority } from "./structure";
import type { TopicStatus } from "./study";
import type { Subject } from "./subject";

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
  subjects: Subject[];
  topics: BookmarkTopic[];
}
