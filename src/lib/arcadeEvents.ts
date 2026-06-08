/**
 * Tiny study-event bus for the arcade coin economy.
 *
 * The coin economy must not be coupled into study features. Study UIs emit a
 * fire-and-forget event when the player completes a study action; the arcade
 * layer (and only the arcade layer) listens and awards coins. If the arcade
 * store isn't mounted, the event is simply ignored — zero impact on studying.
 *
 * This is the single approved seam between the additive game layer and the real
 * app: study components call `emitStudyEvent(...)` and nothing else.
 */

export type StudyEvent = "flashcard" | "mcq";

const EVENT_NAME = "noteration:study-action";

/** Call when the player completes a study action (answers an MCQ, grades a card). */
export function emitStudyEvent(kind: StudyEvent): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent<StudyEvent>(EVENT_NAME, { detail: kind }));
}

/** Subscribe to study actions. Returns an unsubscribe function. */
export function onStudyEvent(handler: (kind: StudyEvent) => void): () => void {
  if (typeof window === "undefined") return () => {};
  const listener = (e: Event) => handler((e as CustomEvent<StudyEvent>).detail);
  window.addEventListener(EVENT_NAME, listener);
  return () => window.removeEventListener(EVENT_NAME, listener);
}
