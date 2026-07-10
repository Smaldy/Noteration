/** Mirrors `backend/schemas/todo.py::TodoItemOut`. */

export interface TodoItem {
  topic_id: number;
  title: string;
  chapter_title: string;
  document_id: number;
  document_filename: string;
  subject_id: number;
  subject_name: string;
  /** The topic's completed flag — the item's checkbox state (shared with the
   *  Notes-tab checkmark and the calendar sync). */
  studied: boolean;
  created_at: string;
}
