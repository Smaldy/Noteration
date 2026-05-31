/** Mirrors `backend/schemas/search.py::SearchResultOut`. */

import type { TopicPriority } from "./structure";
import type { TopicStatus } from "./study";

export type SearchKind = "topic" | "chapter";

export interface SearchResult {
  kind: SearchKind;
  /** topic_id or chapter_id, depending on `kind`. */
  id: number;
  title: string;
  subject_id: number;
  subject_name: string;
  document_id: number;
  document_filename: string;
  chapter_title: string;
  /** Topics only. */
  status: TopicStatus | null;
  priority: TopicPriority | null;
}
