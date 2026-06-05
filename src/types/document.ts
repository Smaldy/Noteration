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

/** `GET /api/documents/{id}/transcript` — an audio document's transcript markdown. */
export interface Transcript {
  document_id: number;
  filename: string;
  markdown: string;
}
