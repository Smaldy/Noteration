/** Mirrors document-shaped responses from `backend/schemas/structure.py`. */

import type { DocumentStatus } from "./library";

export interface DocumentOut {
  id: number;
  subject_id: number;
  filename: string;
  file_hash: string;
  status: DocumentStatus;
}

/** Result of `POST /api/documents` (upload + ingest, before structure review). */
export interface UploadResult {
  document: DocumentOut;
  page_count: number;
  /** No text layer → the client should offer the manual-structure path. */
  is_scanned: boolean;
  /** Large outline-backed book whose markdown is converted lazily per chapter. */
  book_mode: boolean;
}
