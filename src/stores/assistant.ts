import { create } from "zustand";

import { onAiContext } from "@/lib/aiContext";
import { ApiError, api } from "@/lib/api";
import { providerInfo } from "@/lib/providers";
import type {
  ChatAttachmentOut,
  ChatAttachmentsAvailable,
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
  attachments?: ChatAttachmentOut[];
}

/** Accepted attachment types, mirroring the server's allow-list. */
export const ACCEPTED_ATTACHMENTS = "image/png,image/jpeg,image/webp,image/gif,application/pdf";

/** How many files may ride along with one message (the server caps at 8). */
export const MAX_PENDING_ATTACHMENTS = 4;

/** A draft attachment in the composer: uploaded, not yet sent. */
export interface PendingAttachment extends ChatAttachmentOut {
  /** True while its bytes are still going up (chip shows a spinner). */
  uploading?: boolean;
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

/** Negative ids for chips whose upload has not returned a real id yet. */
let draftPlaceholderId = 0;

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
  /** True when the assistant ended this conversation. The transcript stays
   *  readable; the composer locks and only "new chat" moves forward. */
  closed: boolean;
  /** Draft attachments waiting to be sent with the next message. */
  pending: PendingAttachment[];
  /** Whether attachments are possible at all here. `null` until checked; false
   *  on a local-only install, which drives the "not available" state. */
  attachmentsAvailable: boolean | null;
  /** Set when an upload is rejected (wrong type, too big, unreadable PDF). */
  attachmentError: string | null;
  setOpen: (open: boolean) => void;
  toggle: () => void;
  setModel: (model: string) => void;
  setWidth: (px: number) => void;
  resetWidth: () => void;
  setReferenceTopic: (topic: ReferenceTopic | null) => void;
  send: (text: string) => Promise<void>;
  /** Upload files as drafts (from the picker or a Ctrl+V paste). */
  attachFiles: (files: File[]) => Promise<void>;
  /** Remove one draft chip, deleting it server-side. */
  removeAttachment: (id: number) => Promise<void>;
  /** Ask the server whether attachments are possible with these providers. */
  checkAttachmentsAvailable: () => Promise<void>;
  clearAttachmentError: () => void;
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
  closed: false,
  pending: [],
  attachmentsAvailable: null,
  attachmentError: null,

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
        closed: false,
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

  checkAttachmentsAvailable: async () => {
    try {
      const res = await api.get<ChatAttachmentsAvailable>("/chat/attachments/available");
      set({ attachmentsAvailable: res.available });
    } catch {
      // Unreachable server: assume unavailable rather than offering a paperclip
      // that will fail on click.
      set({ attachmentsAvailable: false });
    }
  },

  clearAttachmentError: () => set({ attachmentError: null }),

  attachFiles: async (files) => {
    if (!files.length) return;
    const room = MAX_PENDING_ATTACHMENTS - get().pending.length;
    if (room <= 0) return;
    set({ attachmentError: null });
    for (const file of files.slice(0, room)) {
      // A placeholder chip appears immediately so a large paste doesn't look
      // like nothing happened while its bytes upload.
      const placeholderId = (draftPlaceholderId -= 1);
      set((s) => ({
        pending: [
          ...s.pending,
          {
            id: placeholderId,
            kind: file.type === "application/pdf" ? "pdf" : "image",
            filename: file.name || "pasted image",
            content_type: file.type,
            uploading: true,
          },
        ],
      }));
      const form = new FormData();
      form.append("file", file, file.name || "pasted-image.png");
      try {
        const saved = await api.upload<ChatAttachmentOut>("/chat/attachments", form);
        // Swap the placeholder for the real row, keeping its position.
        set((s) => ({
          pending: s.pending.map((a) =>
            a.id === placeholderId ? { ...saved, uploading: false } : a,
          ),
        }));
      } catch (err) {
        set((s) => ({
          pending: s.pending.filter((a) => a.id !== placeholderId),
          attachmentError: err instanceof ApiError ? err.message : "",
        }));
      }
    }
  },

  removeAttachment: async (id) => {
    set((s) => ({ pending: s.pending.filter((a) => a.id !== id) }));
    // Negative ids are placeholders that never reached the server.
    if (id < 0) return;
    try {
      await api.del(`/chat/attachments/${id}`);
    } catch {
      // The chip is already gone from the UI; a stale draft row is swept
      // server-side, so there is nothing useful to tell the user here.
    }
  },

  send: async (text) => {
    const message = text.trim();
    if (!message || get().sending || get().closed) return;
    // Never send a chip whose bytes are still in flight: its id is a local
    // placeholder the server would reject.
    const attachments = get().pending.filter((a) => !a.uploading && a.id > 0);
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
        { id: localTurnId, role: "user", content: message, attachments },
      ],
      // Cleared optimistically: the chips now belong to the turn above, and a
      // failed send must not silently re-send them with the next message.
      pending: [],
    }));
    const { sessionId, model, referenceTopic } = get();
    const body: ChatSendRequest = {
      session_id: sessionId,
      message,
      provider: model === MODEL_AUTO ? null : model,
      topic_id: referenceTopic?.id ?? null,
      request_id: requestId,
      attachment_ids: attachments.map((a) => a.id),
    };
    try {
      const res = await api.post<ChatSendResponse>("/chat", body, controller.signal);
      set((s) => ({
        sessionId: res.session_id,
        messages: [...s.messages, res.message],
        sending: false,
        // The goodbye turn is shown like any other; what changes is that this
        // thread now refuses further sends.
        closed: res.closed === true,
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
        closed: s.closed_at != null,
        // Composer drafts belong to the thread being left, not the one opened.
        pending: [],
        attachmentError: null,
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
      closed: false,
      pending: [],
      attachmentError: null,
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
        ? { sessionId: null, messages: [], referenceTopic: null, closed: false }
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
