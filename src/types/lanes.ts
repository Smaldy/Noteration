/** Mirrors `backend/schemas/queue.py` lane-aware status + history (Wave C). */

export type LaneState = "running" | "paused" | "overnight" | "waiting";
export type ProviderState = "active" | "cooling" | "disabled";

export interface LaneStatus {
  subject_id: number;
  subject_name: string;
  state: LaneState;
  /** Configured lane state: running / paused / overnight. */
  queue_state: "running" | "paused" | "overnight";
  ready: number;
  processing: number;
  queued: number;
  error: number;
  /** Provider currently running this lane's topic, or null. */
  active_provider: string | null;
  /** Provider this lane is blocked on (when state === "waiting"), or null. */
  waiting_for: string | null;
  /** ISO datetime of this lane's next deferred wake-up, or null. */
  resume_at: string | null;
}

export interface ProviderLaneState {
  provider: string;
  state: ProviderState;
}

export interface LaneQueueStatus {
  lanes: LaneStatus[];
  active_provider: string | null;
  providers: ProviderLaneState[];
}

export type HistoryEventType = "topic_generated" | "provider_switch";

export interface HistoryEvent {
  id: number;
  event_type: HistoryEventType;
  subject_id: number | null;
  subject_name: string | null;
  topic_id: number | null;
  topic_title: string | null;
  provider_from: string | null;
  provider_to: string | null;
  detail: string | null;
  created_at: string;
}
