/** Mirrors `backend/schemas/assessment.py::AggregateAssessmentOut`. */

import type { FlashcardContent, MCQ } from "./study";

export type AssessmentScope = "chapters" | "documents" | "subjects" | "topics";

export interface AggregateAssessment {
  scope: "chapter" | "document" | "subject" | "topics";
  id: number;
  title: string;
  topic_count: number;
  mcqs: MCQ[];
  flashcards: FlashcardContent[];
}

/** Mirrors `backend/schemas/subject.py::SubjectTopicTreeOut` (custom selector). */

export interface SelectableTopic {
  id: number;
  title: string;
  mcq_count: number;
  flashcard_count: number;
}

export interface SelectableChapter {
  id: number;
  title: string;
  topics: SelectableTopic[];
}

export interface SelectableDocument {
  id: number;
  filename: string;
  mode: "study" | "exam";
  chapters: SelectableChapter[];
}

export interface SubjectTopicTree {
  subject_id: number;
  subject_name: string;
  documents: SelectableDocument[];
}
