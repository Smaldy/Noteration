/** Mirrors `backend/schemas/topic.py` (Study View reads). */

import type { TopicPriority } from "./structure";

export type TopicStatus = "queued" | "processing" | "ready" | "error";
// "pending": region detected by the queue, vision transcription not yet run
// (triggered lazily when the topic is opened).
export type FormulaState = "pending" | "reconstructed" | "verified";

// --- document tree (sidebar) ------------------------------------------------

export interface TopicNode {
  id: number;
  title: string;
  priority: TopicPriority;
  status: TopicStatus;
  studied: boolean;
  bookmarked: boolean;
  order_index: number;
}

export interface ChapterNode {
  id: number;
  title: string;
  order_index: number;
  topics: TopicNode[];
}

export interface DocumentTree {
  document_id: number;
  status: "uploaded" | "processing" | "ready" | "error";
  chapters: ChapterNode[];
}

// --- topic content (tabs) ---------------------------------------------------

export interface Formula {
  id: number;
  latex: string;
  state: FormulaState;
  confidence: number | null;
  bbox: Record<string, unknown> | null;
}

export interface Note {
  id: number;
  content_md: string;
  is_manual: boolean;
  locked: boolean;
  stale: boolean;
  formulas: Formula[];
}

export interface MCQ {
  id: number;
  question: string;
  options: string[];
  correct_index: number;
  explanation: string;
  is_manual: boolean;
}

export interface FlashcardContent {
  id: number;
  front: string;
  back: string;
  is_manual: boolean;
}

export interface TopicContent {
  id: number;
  title: string;
  status: TopicStatus;
  studied: boolean;
  bookmarked: boolean;
  notes: Note[];
  mcqs: MCQ[];
  flashcards: FlashcardContent[];
}
