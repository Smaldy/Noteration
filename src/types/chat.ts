/** Mirrors `backend/schemas/chat.py`. */

export interface ChatMessageOut {
  id: number;
  role: "user" | "assistant";
  content: string;
  /** Which provider served an assistant turn; null on user turns. */
  provider: string | null;
  created_at: string;
}

export interface ChatSendRequest {
  /** Omit to start a new session; its id comes back in the response. */
  session_id?: number | null;
  message: string;
  /** Provider name to pin, or null/omitted for the full waterfall. */
  provider?: string | null;
  /** Reference topic to ground the reply on, or null for none. Carried on
   *  every send, like `provider` — sending null removes the chip. */
  topic_id?: number | null;
  /** The client's handle on this send, so the stop button can reach it. */
  request_id?: string | null;
}

/** Stop an in-flight send: its reply is discarded instead of stored. */
export interface ChatStopResponse {
  /** False when the reply had already landed and there was nothing to stop. */
  stopped: boolean;
  /** The session the stopped question went into — a stopped first send never
   *  delivers its response, so this is how the client learns the id. */
  session_id: number | null;
}

export interface ChatSendResponse {
  session_id: number;
  message: ChatMessageOut;
}

/** One history-list entry (no messages). The server caps the list at 5. */
export interface ChatSessionSummary {
  id: number;
  title: string;
  provider: string | null;
  updated_at: string;
}

/** A full session with its transcript, for reopening from history. The topic
 *  fields restore the reference chip (the title is resolved server-side). */
export interface ChatSessionOut extends ChatSessionSummary {
  topic_id: number | null;
  topic_title: string | null;
  messages: ChatMessageOut[];
}
