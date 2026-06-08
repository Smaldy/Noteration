/** Mirrors `backend/schemas/structure.py`. */

export type TopicPriority = "exam_critical" | "medium" | "skip";
/** Per-chapter lane (reuses the subject lane states). Confirm defaults to running. */
export type ChapterQueueState = "running" | "paused" | "overnight";

// --- proposed structure (GET …/structure, read-only) ------------------------

export interface ProposedTopic {
  title: string;
  order_index: number;
  /** Default priority the backend seeds (e.g. `skip` for trash chapters). */
  priority: TopicPriority;
}

export interface ProposedChapter {
  title: string;
  order_index: number;
  topics: ProposedTopic[];
  /** Outline-backed page range (1-indexed inclusive); null for non-outline trees. */
  page_start: number | null;
  page_end: number | null;
}

export interface ProposedStructure {
  chapters: ProposedChapter[];
  /** No headings detected → the user builds the tree manually. */
  needs_manual: boolean;
  method: string;
  /**
   * False → the PDF's markdown has no headings to scope notes by, so each topic
   * is given its slice by reading order. Topic order then matters; the review
   * UI warns about this.
   */
  has_headings: boolean;
}

// --- confirmed structure (POST …/structure, write) --------------------------

export interface TopicIn {
  title: string;
  priority: TopicPriority;
}

export interface ChapterIn {
  title: string;
  topics: TopicIn[];
  /** Per-chapter lane; defaults to running server-side if omitted. */
  queue_state: ChapterQueueState;
  page_start: number | null;
  page_end: number | null;
}

export interface ConfirmStructureIn {
  chapters: ChapterIn[];
  /** ISO date (YYYY-MM-DD) or null. Sets the subject's exam date (deadline mode). */
  exam_date: string | null;
}

export interface ConfirmStructureResult {
  document_id: number;
  chapters_created: number;
  topics_created: number;
  topics_enqueued: number;
}
