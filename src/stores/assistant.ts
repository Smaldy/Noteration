import { create } from "zustand";

import { onAiContext } from "@/lib/aiContext";
import { ApiError, api } from "@/lib/api";
import { providerInfo } from "@/lib/providers";
import type {
  ChatSendRequest,
  ChatSendResponse,
  ChatSessionOut,
  ChatSessionSummary,
  ChatStopResponse,
} from "@/types/chat";

/**
 * AI assistant sidebar state: the current session's thread, the per-session
 * model selection, and the panel chrome (open flag + width).
 *
 * The width is a sticky *global* user preference (localStorage), deliberately
 * separate from chat storage — it survives reloads and new sessions alike.
 */

export const DEFAULT_WIDTH = 384;
export const MIN_WIDTH = 300;
export const MAX_WIDTH = 640;
const WIDTH_KEY = "noteration.assistant.width";

/** The sidebar's model selector value: the full waterfall, or one provider. */
export const MODEL_AUTO = "auto";

/** A displayed thread turn. User turns get a local (negative) id until Step 2
 *  reloads sessions from the server; assistant turns keep their stored id. */
export interface AssistantTurn {
  id: number;
  role: "user" | "assistant";
  content: string;
  provider?: string | null;
}

function clampWidth(px: number): number {
  return Math.min(MAX_WIDTH, Math.max(MIN_WIDTH, Math.round(px)));
}

/** Whether a selector value runs on-device. "Automatic" counts as cloud: the
 *  waterfall may send content to a remote tier. Derived from the provider
 *  registry's tier, never from hardcoded names. */
function isLocalModel(model: string): boolean {
  return model !== MODEL_AUTO && providerInfo(model).tier === "local";
}

function loadWidth(): number {
  try {
    const stored = Number(localStorage.getItem(WIDTH_KEY));
    if (Number.isFinite(stored) && stored > 0) return clampWidth(stored);
  } catch {
    // storage unavailable (private mode) — fall through to the default
  }
  return DEFAULT_WIDTH;
}

function persistWidth(px: number): void {
  try {
    localStorage.setItem(WIDTH_KEY, String(px));
  } catch {
    // best-effort only
  }
}

let localTurnId = 0;

/** The send currently in flight, if any — what the stop button acts on. */
let inFlight: { id: string; controller: AbortController } | null = null;

function newRequestId(): string {
  if (typeof crypto?.randomUUID === "function") return crypto.randomUUID();
  return `req-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}

/** The reference-topic chip: the topic whose material grounds this session. */
export interface ReferenceTopic {
  id: number;
  title: string;
}

interface AssistantStore {
  open: boolean;
  width: number;
  /** `MODEL_AUTO` or a provider name (e.g. "gemini_free", "ollama"). */
  model: string;
  sessionId: number | null;
  messages: AssistantTurn[];
  sending: boolean;
  error: string | null;
  /** The last-5 history list (server-capped), newest first. */
  sessions: ChatSessionSummary[];
  /** Pinned reference topic, or null. Sent with every message. */
  referenceTopic: ReferenceTopic | null;
  /** Set when the user stopped the last reply, cleared on the next send. */
  stopped: boolean;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  setModel: (model: string) => void;
  setWidth: (px: number) => void;
  resetWidth: () => void;
  setReferenceTopic: (topic: ReferenceTopic | null) => void;
  send: (text: string) => Promise<void>;
  /** Stop the reply being generated: the answer is discarded, not stored. */
  stop: () => void;
  fetchSessions: () => Promise<void>;
  openSession: (id: number) => Promise<void>;
  newSession: () => void;
  deleteSession: (id: number) => Promise<void>;
}

export const useAssistantStore = create<AssistantStore>((set, get) => ({
  open: false,
  width: loadWidth(),
  model: MODEL_AUTO,
  sessionId: null,
  messages: [],
  sending: false,
  error: null,
  sessions: [],
  referenceTopic: null,
  stopped: false,

  setOpen: (open) => set({ open }),
  toggle: () => set((s) => ({ open: !s.open })),

  // The provider-switch rule: within the same type (cloud → cloud) the session
  // continues; crossing local ↔ cloud forks — the current thread is already
  // saved (table-backed), so just open a fresh one. The privacy context
  // changed; the old transcript must not silently ride along to the other side.
  setModel: (model) => {
    const { model: prev, messages } = get();
    if (model === prev) return;
    const crossed = isLocalModel(prev) !== isLocalModel(model);
    if (crossed && messages.length > 0) {
      // The pinned topic's material is grounding context — it must not silently
      // ride along across the privacy line either. Re-pin explicitly.
      set({
        model,
        sessionId: null,
        messages: [],
        referenceTopic: null,
        error: null,
      });
    } else {
      set({ model });
    }
  },

  setWidth: (px) => {
    const width = clampWidth(px);
    persistWidth(width);
    set({ width });
  },
  resetWidth: () => {
    persistWidth(DEFAULT_WIDTH);
    set({ width: DEFAULT_WIDTH });
  },

  // The chip is session state, not a one-shot: it rides along with every send
  // until removed, and the server records the latest value (null = unpinned).
  setReferenceTopic: (topic) => set({ referenceTopic: topic }),

  send: async (text) => {
    const message = text.trim();
    if (!message || get().sending) return;
    localTurnId -= 1;
    // A fresh handle per send: the stop button aborts this request and tells
    // the server to bin the reply it is already working on.
    inFlight = { id: newRequestId(), controller: new AbortController() };
    const { id: requestId, controller } = inFlight;
    set((s) => ({
      sending: true,
      error: null,
      stopped: false,
      messages: [
        ...s.messages,
        { id: localTurnId, role: "user", content: message },
      ],
    }));
    const { sessionId, model, referenceTopic } = get();
    const body: ChatSendRequest = {
      session_id: sessionId,
      message,
      provider: model === MODEL_AUTO ? null : model,
      topic_id: referenceTopic?.id ?? null,
      request_id: requestId,
    };
    try {
      const res = await api.post<ChatSendResponse>("/chat", body, controller.signal);
      set((s) => ({
        sessionId: res.session_id,
        messages: [...s.messages, res.message],
        sending: false,
      }));
    } catch (err) {
      // The abort is the user's own doing: `stop` has already set the state,
      // and there is nothing to report.
      if (err instanceof DOMException && err.name === "AbortError") return;
      // "" = failed with no useful detail; the UI shows its generic line then.
      set({
        sending: false,
        error: err instanceof ApiError ? err.message : "",
      });
    } finally {
      if (inFlight?.id === requestId) inFlight = null;
    }
  },

  stop: () => {
    if (!inFlight || !get().sending) return;
    const { id, controller } = inFlight;
    inFlight = null;
    // Stop both ends: drop the response we are waiting on, and tell the server
    // to discard the reply when the provider finally returns it — otherwise it
    // would be stored and reappear the next time this session is opened.
    controller.abort();
    void api
      .post<ChatStopResponse>("/chat/stop", { request_id: id })
      .then((res) => {
        // A stopped *first* send never delivers its response, so this is where
        // we learn the session id. Without adopting it, the next message would
        // open a second session while the panel still showed one thread.
        if (res.session_id !== null && get().sessionId === null) {
          set({ sessionId: res.session_id });
        }
      })
      .catch(() => {
        // Best effort: a stop that misses only means the reply was already stored.
      });
    set({ sending: false, stopped: true, error: null });
  },

  fetchSessions: async () => {
    try {
      set({ sessions: await api.get<ChatSessionSummary[]>("/chat/sessions") });
    } catch {
      // History is a convenience; a failed fetch just leaves the list as-is.
    }
  },

  openSession: async (id) => {
    try {
      const s = await api.get<ChatSessionOut>(`/chat/sessions/${id}`);
      set({
        sessionId: s.id,
        messages: s.messages,
        model: s.provider ?? MODEL_AUTO,
        stopped: false,
        // A reopened session comes back with its chip (the topic may have been
        // deleted since, in which case the server already unpinned it).
        referenceTopic:
          s.topic_id !== null && s.topic_title !== null
            ? { id: s.topic_id, title: s.topic_title }
            : null,
        error: null,
      });
    } catch (err) {
      set({ error: err instanceof ApiError ? err.message : "" });
    }
  },

  newSession: () =>
    set({
      sessionId: null,
      messages: [],
      error: null,
      referenceTopic: null,
      stopped: false,
    }),

  deleteSession: async (id) => {
    try {
      await api.del(`/chat/sessions/${id}`);
    } catch {
      // Already gone (e.g. evicted) — dropping it from the list below is right.
    }
    set((s) => ({
      sessions: s.sessions.filter((x) => x.id !== id),
      // Deleting the open session clears the thread (and its chip) too.
      ...(s.sessionId === id
        ? { sessionId: null, messages: [], referenceTopic: null }
        : {}),
    }));
  },
}));

// The context emitters (note selection, card explainers) all feed the same
// thread through one event: open the sidebar and send the quoted source plus
// the instruction as a normal user turn. It APPENDS to whatever session is
// open — an emitter never wipes an ongoing conversation.
onAiContext(({ text, instruction }) => {
  const store = useAssistantStore.getState();
  store.setOpen(true);
  const quoted = text
    .trim()
    .split("\n")
    .map((line) => `> ${line}`)
    .join("\n");
  void store.send(`${quoted}\n\n${instruction}`);
});

/** How far fixed chrome (floating widgets, provider badge) must shift left so
 *  the docked panel doesn't cover it. */
export function useAssistantOffset(): number {
  return useAssistantStore((s) => (s.open ? s.width : 0));
}
