/** Mirrors document-shaped responses from `backend/schemas/structure.py`. */

import type { DocumentStatus, SourceType } from "./library";

export interface DocumentOut {
  id: number;
  subject_id: number;
  filename: string;
  file_hash: string;
  status: DocumentStatus;
  status_detail?: string | null;
  source_type: SourceType;
}

/** Which assessment types an Exam Prep upload generates. Mirrors
 *  `ExamQuestionTypes` in `backend/models/enums.py`. */
export type ExamQuestionTypes = "mcq" | "flashcards" | "both";

/** The Exam Prep upload's generation choices, recorded on the document.
 *  `ai_style` of null means follow the global Settings writing style. */
export interface ExamGenerationOptions {
  question_types: ExamQuestionTypes;
  ai_style: string | null;
}

/** Result of `POST /api/documents` (upload, before structure review).
 *  Audio uploads have no ingest yet (transcribed in the background), so the
 *  page_count/is_scanned/book_mode fields default and status is "transcribing". */
export interface UploadResult {
  document: DocumentOut;
  page_count: number;
  /** No text layer → the client should offer the manual-structure path. */
  is_scanned: boolean;
  /** Large outline-backed book whose markdown is converted lazily per chapter. */
  book_mode: boolean;
}

/** One file's outcome in an overnight batch (`POST /api/documents/batch`). */
export interface BatchItemResult {
  filename: string;
  ok: boolean;
  document_id: number | null;
  topics_enqueued: number;
  error: string | null;
}

/** Result of an overnight batch upload: per-file results plus totals. */
export interface BatchUploadResult {
  subject_id: number;
  documents_ok: number;
  topics_enqueued: number;
  items: BatchItemResult[];
}

/** `GET /api/documents/{id}/transcript` — an audio document's transcript markdown. */
export interface Transcript {
  document_id: number;
  filename: string;
  markdown: string;
}
