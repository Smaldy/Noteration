import { AnimatePresence, motion } from "framer-motion";
import {
  BookMarked,
  Check,
  Copy,
  History,
  MoveHorizontal,
  NotebookPen,
  PictureInPicture2,
  Plus,
  SendHorizontal,
  Sparkles,
  Square,
  Trash2,
  X,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownView } from "@/components/MarkdownView";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { PROVIDER_NAMES, providerInfo } from "@/lib/providers";
import { cn } from "@/lib/utils";
import {
  type AssistantTurn,
  MODEL_AUTO,
  useAssistantStore,
} from "@/stores/assistant";
import { useSettingsStore } from "@/stores/settings";
import type { Settings } from "@/types/settings";

import { ReferenceTopicDialog } from "./ReferenceTopicDialog";
import { SaveNoteDialog } from "./SaveNoteDialog";

/**
 * The docked AI sidebar — the app's only chat surface. One engine, several
 * entry points (free chat now; selection/card emitters arrive in later steps).
 *
 * - Model selector is per-session: "Automatic" is the settings waterfall, or
 *   pin one provider (Ollama is flagged private/local with its amber tier dot).
 * - Replies render in the reading face (the Settings font when the user picked
 *   one, a serif otherwise); user turns stay in the UI sans, so the speaker
 *   distinction is typographic, not just alignment.
 * - A reply being generated can be stopped: the request is aborted and the
 *   server discards the answer instead of storing it.
 * - The left edge drags to resize; the width is a sticky global preference.
 */
export function AssistantSidebar() {
  const { t } = useTranslation();
  const open = useAssistantStore((s) => s.open);
  const width = useAssistantStore((s) => s.width);

  return (
    <AnimatePresence>
      {open && (
        <motion.aside
          aria-label={t("assistant.title")}
          initial={{ x: width + 24 }}
          animate={{ x: 0 }}
          exit={{ x: width + 24 }}
          transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
          style={{ width }}
          className="fixed inset-y-0 right-0 z-40 flex flex-col border-l bg-card shadow-2xl print:hidden"
        >
          <Panel />
        </motion.aside>
      )}
    </AnimatePresence>
  );
}

/** Panel body — owns the history slide-over state. */
function Panel() {
  const [historyOpen, setHistoryOpen] = useState(false);
  return (
    <>
      <ResizeHandle />
      <Header historyOpen={historyOpen} onToggleHistory={() => setHistoryOpen((v) => !v)} />
      <div className="relative flex min-h-0 flex-1 flex-col">
        <Thread />
        <AnimatePresence>
          {historyOpen && <HistoryPanel onClose={() => setHistoryOpen(false)} />}
        </AnimatePresence>
      </div>
      <Composer />
    </>
  );
}

/** Edge-drag resize: pointer capture keeps the drag alive outside the strip. */
function ResizeHandle() {
  const setWidth = useAssistantStore((s) => s.setWidth);
  return (
    <div
      role="separator"
      aria-orientation="vertical"
      onPointerDown={(e) => e.currentTarget.setPointerCapture(e.pointerId)}
      onPointerMove={(e) => {
        if (e.currentTarget.hasPointerCapture(e.pointerId)) {
          setWidth(window.innerWidth - e.clientX);
        }
      }}
      className="absolute inset-y-0 left-0 z-10 w-1.5 cursor-col-resize touch-none select-none transition-colors hover:bg-primary/40 active:bg-primary/60"
    />
  );
}

function Header({
  historyOpen,
  onToggleHistory,
}: {
  historyOpen: boolean;
  onToggleHistory: () => void;
}) {
  const { t } = useTranslation();
  const setOpen = useAssistantStore((s) => s.setOpen);
  const resetWidth = useAssistantStore((s) => s.resetWidth);
  const newSession = useAssistantStore((s) => s.newSession);

  return (
    <div className="border-b px-4 pb-3 pt-3.5">
      <div className="flex items-center justify-between">
        <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.12em] text-primary">
          <Sparkles className="size-4" />
          {t("assistant.title")}
        </span>
        <div className="flex items-center gap-0.5">
          <HeaderButton
            title={t("assistant.newChat")}
            onClick={newSession}
            icon={<Plus className="size-4" />}
          />
          <HeaderButton
            title={t("assistant.history")}
            onClick={onToggleHistory}
            active={historyOpen}
            icon={<History className="size-4" />}
          />
          {/* Float mode ships later — the affordance reserves its spot. */}
          <HeaderButton
            title={t("assistant.floatSoon")}
            disabled
            icon={<PictureInPicture2 className="size-4" />}
          />
          <HeaderButton
            title={t("assistant.resetWidth")}
            onClick={resetWidth}
            icon={<MoveHorizontal className="size-4" />}
          />
          <HeaderButton
            title={t("assistant.close")}
            onClick={() => setOpen(false)}
            icon={<X className="size-4" />}
          />
        </div>
      </div>
      <ModelSelect />
      <ReferenceChip />
    </div>
  );
}

/** The reference-topic chip: what the assistant is grounded on right now.
 *  The label reopens the picker to change it; the ✕ unpins it. */
function ReferenceChip() {
  const { t } = useTranslation();
  const topic = useAssistantStore((s) => s.referenceTopic);
  const setReferenceTopic = useAssistantStore((s) => s.setReferenceTopic);
  const [pickerOpen, setPickerOpen] = useState(false);

  return (
    <div className="mt-2 flex">
      {topic ? (
        <span className="inline-flex min-w-0 max-w-full items-center gap-1 rounded-full border border-primary/30 bg-primary/10 py-0.5 pl-2 pr-0.5 text-xs text-primary">
          <BookMarked className="size-3 shrink-0" />
          <button
            type="button"
            onClick={() => setPickerOpen(true)}
            title={t("assistant.reference.change")}
            className="min-w-0 truncate py-0.5 hover:underline"
          >
            {topic.title}
          </button>
          <button
            type="button"
            onClick={() => setReferenceTopic(null)}
            title={t("assistant.reference.remove")}
            aria-label={t("assistant.reference.remove")}
            className="shrink-0 rounded-full p-1 transition-colors hover:bg-primary/20"
          >
            <X className="size-3" />
          </button>
        </span>
      ) : (
        <button
          type="button"
          onClick={() => setPickerOpen(true)}
          className="inline-flex items-center gap-1.5 rounded-full border border-dashed px-2.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/50 hover:text-foreground"
        >
          <BookMarked className="size-3" />
          {t("assistant.reference.add")}
        </button>
      )}
      <ReferenceTopicDialog open={pickerOpen} onOpenChange={setPickerOpen} />
    </div>
  );
}

function HeaderButton({
  title,
  icon,
  onClick,
  disabled,
  active,
}: {
  title: string;
  icon: React.ReactNode;
  onClick?: () => void;
  disabled?: boolean;
  active?: boolean;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "rounded-md p-1.5 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground disabled:opacity-40 disabled:hover:bg-transparent",
        active && "bg-muted text-foreground",
      )}
    >
      {icon}
    </button>
  );
}

/** The last-5 history list, sliding over the thread. Picking a session loads
 *  its transcript (and its pinned model) into the sidebar. */
function HistoryPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation();
  const sessions = useAssistantStore((s) => s.sessions);
  const fetchSessions = useAssistantStore((s) => s.fetchSessions);
  const openSession = useAssistantStore((s) => s.openSession);
  const deleteSession = useAssistantStore((s) => s.deleteSession);

  useEffect(() => {
    void fetchSessions();
  }, [fetchSessions]);

  return (
    <motion.div
      initial={{ opacity: 0, y: -8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -8 }}
      transition={{ duration: 0.16 }}
      className="absolute inset-0 z-10 overflow-y-auto bg-card p-2"
    >
      {sessions.length === 0 ? (
        <p className="px-2 py-6 text-center text-sm text-muted-foreground">
          {t("assistant.noHistory")}
        </p>
      ) : (
        <ul className="space-y-1">
          {sessions.map((s) => (
            <li key={s.id} className="group flex items-center gap-1">
              <button
                type="button"
                onClick={() => {
                  void openSession(s.id);
                  onClose();
                }}
                className="min-w-0 flex-1 rounded-lg px-3 py-2 text-left transition-colors hover:bg-muted"
              >
                <span className="block truncate text-sm">{s.title || "…"}</span>
                <span className="mt-0.5 flex items-center gap-1.5 text-[10px] text-muted-foreground">
                  {s.provider && (
                    <span
                      className={cn(
                        "size-1.5 rounded-full",
                        providerInfo(s.provider).dot,
                      )}
                    />
                  )}
                  {new Date(s.updated_at).toLocaleString(undefined, {
                    dateStyle: "short",
                    timeStyle: "short",
                  })}
                </span>
              </button>
              <button
                type="button"
                title={t("assistant.deleteChat")}
                aria-label={t("assistant.deleteChat")}
                onClick={() => void deleteSession(s.id)}
                className="rounded-md p-1.5 text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
              >
                <Trash2 className="size-3.5" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </motion.div>
  );
}

/** Whether a provider is actually usable with the current settings — shown
 *  disabled (but visible) otherwise, so the list mirrors the Settings page. */
function providerReady(name: string, settings: Settings | null): boolean {
  if (!settings) return true;
  if (name === "gemini_free") {
    return settings.gemini_key_set && settings.gemini_enabled;
  }
  if (name === "ollama") {
    return settings.ollama_enabled && !!settings.ollama_model;
  }
  return true;
}

function ModelSelect() {
  const { t } = useTranslation();
  const model = useAssistantStore((s) => s.model);
  const setModel = useAssistantStore((s) => s.setModel);
  const settings = useSettingsStore((s) => s.settings);

  return (
    <Select value={model} onValueChange={setModel}>
      <SelectTrigger className="mt-2.5 h-8 w-full text-xs">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={MODEL_AUTO} className="text-xs">
          <span className="inline-flex items-center gap-2">
            <span className="size-2 rounded-full bg-primary" />
            {t("assistant.modelAuto")}
            <span className="text-muted-foreground">
              {t("assistant.modelAutoHint")}
            </span>
          </span>
        </SelectItem>
        {PROVIDER_NAMES.map((name) => {
          const info = providerInfo(name);
          return (
            <SelectItem
              key={name}
              value={name}
              disabled={!providerReady(name, settings)}
              className="text-xs"
            >
              <span className="inline-flex items-center gap-2">
                <span className={cn("size-2 rounded-full", info.dot)} />
                {info.label}
                {info.tier === "local" && (
                  <span className="text-muted-foreground">
                    {t("assistant.localHint")}
                  </span>
                )}
              </span>
            </SelectItem>
          );
        })}
      </SelectContent>
    </Select>
  );
}

/** The wait state. With a topic pinned it names what the assistant is reading:
 *  the sidebar says what it is actually doing, not a generic "working on it". */
function Pending() {
  const { t } = useTranslation();
  const topic = useAssistantStore((s) => s.referenceTopic);
  return (
    <div className="flex items-center gap-2 text-sm text-muted-foreground">
      <span className="thinking-dots" aria-hidden>
        <span />
        <span />
        <span />
      </span>
      <span className="min-w-0 truncate">
        {topic
          ? t("assistant.reading", { topic: topic.title })
          : t("assistant.thinking")}
      </span>
    </div>
  );
}

function Thread() {
  const { t } = useTranslation();
  const messages = useAssistantStore((s) => s.messages);
  const sending = useAssistantStore((s) => s.sending);
  const stopped = useAssistantStore((s) => s.stopped);
  const scrollRef = useRef<HTMLDivElement>(null);

  // "Save as note" flow: one dialog for the whole thread, armed with the turn
  // being saved; the source turn flashes its Saved state after success.
  const [saveTurn, setSaveTurn] = useState<AssistantTurn | null>(null);
  const [savedId, setSavedId] = useState<number | null>(null);

  useEffect(() => {
    if (savedId === null) return;
    const timer = setTimeout(() => setSavedId(null), 2000);
    return () => clearTimeout(timer);
  }, [savedId]);

  // Keep the newest turn in view as the thread grows.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages.length, sending, stopped]);

  if (messages.length === 0 && !sending) {
    return (
      <div className="flex flex-1 items-center justify-center px-8 text-center">
        <p className="text-sm text-muted-foreground">{t("assistant.empty")}</p>
      </div>
    );
  }

  return (
    <div ref={scrollRef} className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
      {messages.map((m) => (
        <Turn
          key={m.id}
          turn={m}
          saved={savedId === m.id}
          onSave={() => setSaveTurn(m)}
        />
      ))}
      {sending && <Pending />}
      {stopped && (
        <p className="text-xs text-muted-foreground">{t("assistant.stoppedNote")}</p>
      )}
      <SaveNoteDialog
        open={saveTurn !== null}
        onOpenChange={(open) => {
          if (!open) setSaveTurn(null);
        }}
        content={saveTurn?.content ?? ""}
        onSaved={() => {
          if (saveTurn) setSavedId(saveTurn.id);
        }}
      />
    </div>
  );
}

/** Split a user turn into its leading `> ` quote block (the source text an
 *  aiContext emitter attached) and the instruction that follows it. */
function splitQuote(content: string): { quote: string | null; rest: string } {
  if (!content.startsWith(">")) return { quote: null, rest: content };
  const lines = content.split("\n");
  const quoteLines: string[] = [];
  let i = 0;
  while (i < lines.length && lines[i].startsWith(">")) {
    quoteLines.push(lines[i].replace(/^> ?/, ""));
    i += 1;
  }
  while (i < lines.length && lines[i].trim() === "") i += 1;
  return { quote: quoteLines.join("\n"), rest: lines.slice(i).join("\n") };
}

/** Copy markdown to the clipboard, with a hidden-textarea fallback for
 *  webviews that lack the async clipboard API. */
async function copyText(text: string): Promise<boolean> {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    ta.remove();
    return ok;
  }
}

function Turn({
  turn,
  saved,
  onSave,
}: {
  turn: AssistantTurn;
  saved: boolean;
  onSave: () => void;
}) {
  const { t } = useTranslation();
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);

  if (turn.role === "user") {
    const { quote, rest } = splitQuote(turn.content);
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-primary px-3.5 py-2 text-sm text-primary-foreground">
          {quote && (
            <blockquote className="mb-1.5 line-clamp-6 whitespace-pre-wrap border-l-2 border-primary-foreground/40 pl-2 text-xs text-primary-foreground/85">
              {quote}
            </blockquote>
          )}
          <div className="whitespace-pre-wrap">{rest}</div>
        </div>
      </div>
    );
  }
  const info = providerInfo(turn.provider);
  return (
    <div className="space-y-1">
      {turn.provider && (
        <span className="inline-flex items-center gap-1.5 text-[10px] font-medium text-muted-foreground">
          <span className={cn("size-1.5 rounded-full", info.dot)} />
          {info.short}
        </span>
      )}
      {/* Answers take the reading face (the Settings font when one is set),
          questions stay in the UI sans — the speaker reads at a glance. */}
      <div className="assistant-reply">
        <MarkdownView>{turn.content}</MarkdownView>
      </div>
      {/* Exactly two actions per reply: save it as a note, or copy it. */}
      <div className="flex items-center gap-1 pt-0.5">
        <ReplyAction
          label={saved ? t("assistant.actions.saved") : t("assistant.actions.save")}
          icon={
            saved ? <Check className="size-3.5" /> : <NotebookPen className="size-3.5" />
          }
          onClick={onSave}
        />
        <ReplyAction
          label={copied ? t("assistant.actions.copied") : t("assistant.actions.copy")}
          icon={copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />}
          onClick={() => {
            void copyText(turn.content).then((ok) => setCopied(ok));
          }}
        />
      </div>
    </div>
  );
}

function ReplyAction({
  label,
  icon,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
    >
      {icon}
      {label}
    </button>
  );
}

function Composer() {
  const { t } = useTranslation();
  const send = useAssistantStore((s) => s.send);
  const stop = useAssistantStore((s) => s.stop);
  const sending = useAssistantStore((s) => s.sending);
  const error = useAssistantStore((s) => s.error);
  const [draft, setDraft] = useState("");

  const submit = () => {
    const text = draft.trim();
    if (!text || sending) return;
    setDraft("");
    void send(text);
  };

  return (
    <div className="border-t px-3 pb-3 pt-2.5">
      {error !== null && (
        <p className="mb-2 text-xs text-destructive">
          {error || t("assistant.error")}
        </p>
      )}
      <div className="flex items-end gap-2">
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          placeholder={t("assistant.placeholder")}
          className="max-h-40 min-h-[2.5rem] flex-1 resize-none rounded-xl border bg-background px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-ring"
        />
        {/* One control, two states: while a reply is generating the send button
            becomes the stop button, so the action is always where the hand is. */}
        {sending ? (
          <button
            type="button"
            onClick={stop}
            title={t("assistant.stop")}
            aria-label={t("assistant.stop")}
            className="flex size-9 shrink-0 items-center justify-center rounded-xl border border-primary/40 bg-primary/10 text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
          >
            <Square className="size-3.5 fill-current" />
          </button>
        ) : (
          <button
            type="button"
            onClick={submit}
            disabled={!draft.trim()}
            title={t("assistant.send")}
            aria-label={t("assistant.send")}
            className="flex size-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background disabled:opacity-40"
          >
            <SendHorizontal className="size-4" />
          </button>
        )}
      </div>
    </div>
  );
}
