/** Mirrors `backend/schemas/structure.py`. */

export type TopicPriority = "exam_critical" | "medium" | "skip";

// --- proposed structure (GET …/structure, read-only) ------------------------

export interface ProposedTopic {
  title: string;
  order_index: number;
}

export interface ProposedChapter {
  title: string;
  order_index: number;
  topics: ProposedTopic[];
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
