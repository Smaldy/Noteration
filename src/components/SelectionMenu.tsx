import { SendHorizontal, Sparkles } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";

import { emitAiContext } from "@/lib/aiContext";

/**
 * Floating "ask the assistant" menu for text selected inside a MarkdownView.
 * Three presets plus a free-text field; every choice emits one aiContext
 * event (the only seam to the sidebar) carrying the selection + instruction.
 *
 * The selected text is captured when the menu opens, so clicking into the
 * free-text field (which collapses the browser selection) can't lose it.
 */

interface Anchor {
  text: string;
  /** Viewport coordinates of the selection rectangle's top center. */
  x: number;
  y: number;
}

const PRESETS = [
  { labelKey: "assistant.selection.explainSimply", promptKey: "assistant.selection.explainSimplyPrompt" },
  { labelKey: "assistant.selection.summarize", promptKey: "assistant.selection.summarizePrompt" },
  { labelKey: "assistant.selection.explainTechnical", promptKey: "assistant.selection.explainTechnicalPrompt" },
] as const;

export function SelectionMenu({
  container,
}: {
  container: RefObject<HTMLDivElement | null>;
}) {
  const { t } = useTranslation();
  const [anchor, setAnchor] = useState<Anchor | null>(null);
  const [draft, setDraft] = useState("");
  const menuRef = useRef<HTMLDivElement>(null);

  // Open on a finished selection gesture inside this view.
  useEffect(() => {
    const el = container.current;
    if (!el) return;
    const onMouseUp = () => {
      // Defer one tick so the browser has finalized the selection.
      setTimeout(() => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || sel.rangeCount === 0) return;
        const range = sel.getRangeAt(0);
        if (!el.contains(range.commonAncestorContainer)) return;
        const text = sel.toString().trim();
        if (!text) return;
        const rect = range.getBoundingClientRect();
        setAnchor({ text, x: rect.left + rect.width / 2, y: rect.top });
        setDraft("");
      }, 0);
    };
    el.addEventListener("mouseup", onMouseUp);
    return () => el.removeEventListener("mouseup", onMouseUp);
  }, [container]);

  // A press outside the menu (or Escape) dismisses it.
  useEffect(() => {
    if (!anchor) return;
    const onDown = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setAnchor(null);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setAnchor(null);
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [anchor]);

  if (!anchor) return null;

  const ask = (instruction: string) => {
    emitAiContext({ text: anchor.text, instruction });
    setAnchor(null);
    window.getSelection()?.removeAllRanges();
  };

  const half = 148;
  const left = Math.min(Math.max(anchor.x, half), window.innerWidth - half);
  // Sits above the selection; near the viewport top it clamps down instead.
  const top = Math.max(anchor.y - 8, 110);

  return createPortal(
    <div
      ref={menuRef}
      role="menu"
      aria-label={t("assistant.selection.menuAria")}
      style={{ left, top }}
      className="fixed z-50 w-72 -translate-x-1/2 -translate-y-full rounded-xl border bg-popover p-2 text-popover-foreground shadow-xl"
    >
      <div className="flex flex-wrap items-center gap-1">
        <Sparkles className="ml-0.5 size-3.5 shrink-0 text-primary" />
        {PRESETS.map(({ labelKey, promptKey }) => (
          <button
            key={labelKey}
            type="button"
            onClick={() => ask(t(promptKey))}
            className="rounded-md border px-2 py-1 text-xs transition-colors hover:bg-muted"
          >
            {t(labelKey)}
          </button>
        ))}
      </div>
      <div className="mt-1.5 flex items-center gap-1">
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && draft.trim()) ask(draft.trim());
          }}
          placeholder={t("assistant.selection.placeholder")}
          className="h-7 min-w-0 flex-1 rounded-md border bg-background px-2 text-xs outline-none transition-colors placeholder:text-muted-foreground focus:border-ring"
        />
        <button
          type="button"
          disabled={!draft.trim()}
          onClick={() => ask(draft.trim())}
          title={t("assistant.selection.askAria")}
          aria-label={t("assistant.selection.askAria")}
          className="flex size-7 shrink-0 items-center justify-center rounded-md bg-primary text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-40"
        >
          <SendHorizontal className="size-3.5" />
        </button>
      </div>
    </div>,
    document.body,
  );
}
