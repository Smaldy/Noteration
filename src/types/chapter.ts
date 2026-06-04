/** Mirrors `backend/schemas/chapter.py` (Chapter Lanes). */

export type ChapterQueueState = "running" | "paused" | "overnight";

export interface ChapterStatus {
  id: number;
  title: string;
  page_start: number | null;
  page_end: number | null;
  queue_state: ChapterQueueState;
  topics_total: number;
  topics_ready: number;
  topics_processing: number;
  topics_queued: number;
  topics_error: number;
}

/** A book's chapter lanes grouped under its document (Queue page). */
export interface DocumentChapters {
  document_id: number;
  filename: string;
  subject_id: number;
  subject_name: string;
  chapters: ChapterStatus[];
}
