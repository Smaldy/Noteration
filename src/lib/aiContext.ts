/**
 * Tiny context-event bus for the AI assistant sidebar.
 *
 * Study surfaces (note text selection now, card explainers later) emit a
 * fire-and-forget event carrying the source text plus an instruction; the
 * assistant store is the only listener and appends it to the open thread as a
 * quoted user turn. Modeled on `arcadeEvents.ts`: this is the single approved
 * seam between study UIs and the sidebar, so emitters never import chat
 * internals — if the sidebar isn't mounted yet, the store still receives it.
 */

export interface AiContextEvent {
  /** The source text (selection, card, …) — rendered quoted in the thread. */
  text: string;
  /** What to do with it: a preset sentence or the user's free-text question. */
  instruction: string;
}

const EVENT_NAME = "noteration:ai-context";

/** Send source text + instruction to the assistant (opens the sidebar). */
export function emitAiContext(detail: AiContextEvent): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<AiContextEvent>(EVENT_NAME, { detail }));
}

/** Subscribe to context events. Returns an unsubscribe function. */
export function onAiContext(
  handler: (event: AiContextEvent) => void,
): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) =>
    handler((e as CustomEvent<AiContextEvent>).detail);
  window.addEventListener(EVENT_NAME, listener);
  return () => window.removeEventListener(EVENT_NAME, listener);
}
