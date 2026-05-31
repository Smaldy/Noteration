/** Mirrors `backend/schemas/queue.py`. */

export interface QueueErrorTopic {
  topic_id: number;
  title: string;
  last_error: string | null;
}

export interface QueueStatus {
  ready: number;
  processing: number;
  queued: number;
  error: number;
  total: number;
  /** ISO datetime of the next provider-window wake-up, or null. */
  resume_at: string | null;
  /** Why work is paused (recorded provider error behind `resume_at`), or null. */
  paused_reason: string | null;
  /** Tokens a document has spent / its ceiling, and whether it's paused on budget. */
  token_spent: number;
  token_budget: number;
  budget_paused: boolean;
  errors: QueueErrorTopic[];
}
