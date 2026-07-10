import { AnimatePresence, motion } from "framer-motion";
import { Check, CheckCheck, ChevronDown, ListTodo, Plus, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { cn } from "@/lib/utils";
import { useStudyStore } from "@/stores/study";
import { useTodoStore } from "@/stores/todo";
import type { TodoItem } from "@/types/todo";

import { TodoAddDialog } from "./TodoAddDialog";

/**
 * The floating to-do list — a sibling of the Pomodoro widget (same collapsed
 * pill / expanded glass panel pattern). Items are pinned topics; the checkbox
 * is the topic's completed/studied flag, shared with the Notes tab and the
 * calendar, so ticking it anywhere ticks it everywhere.
 */
export function TodoWidget() {
  const { t } = useTranslation();
  const items = useTodoStore((s) => s.items);
  const fetchItems = useTodoStore((s) => s.fetch);
  const clearCompleted = useTodoStore((s) => s.clearCompleted);
  const [expanded, setExpanded] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  useEffect(() => {
    void fetchItems();
  }, [fetchItems]);

  const remaining = items.filter((i) => !i.studied).length;
  const doneCount = items.length - remaining;

  return (
    <>
      <AnimatePresence mode="wait" initial={false}>
        {expanded ? (
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="glass w-80 rounded-2xl border p-4 shadow-xl"
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.12em] text-primary">
                <ListTodo className="size-4" />
                {t("todo.title")}
                {items.length > 0 && (
                  <span className="font-semibold normal-case tracking-normal text-muted-foreground">
                    {t("todo.progress", { done: doneCount, total: items.length })}
                  </span>
                )}
              </span>
              <div className="flex items-center gap-0.5">
                <button
                  type="button"
                  onClick={() => setPickerOpen(true)}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  title={t("todo.addTopics")}
                  aria-label={t("todo.addTopics")}
                >
                  <Plus className="size-4" />
                </button>
                <button
                  type="button"
                  onClick={() => setExpanded(false)}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                  title={t("todo.minimize")}
                  aria-label={t("todo.minimize")}
                >
                  <ChevronDown className="size-4" />
                </button>
              </div>
            </div>

            {items.length === 0 ? (
              <p className="mt-3 rounded-lg border border-dashed px-4 py-6 text-center text-xs leading-relaxed text-muted-foreground">
                {t("todo.empty")}
              </p>
            ) : (
              <ul className="-mx-1.5 mt-2 max-h-72 space-y-0.5 overflow-y-auto px-1.5">
                {items.map((item) => (
                  <TodoRow key={item.topic_id} item={item} />
                ))}
              </ul>
            )}

            {doneCount > 0 && (
              <button
                type="button"
                onClick={() => void clearCompleted()}
                className="mt-3 flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:border-ring/40 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              >
                <CheckCheck className="size-3.5" />
                {t("todo.clearCompleted", { count: doneCount })}
              </button>
            )}
          </motion.div>
        ) : (
          <motion.button
            key="pill"
            type="button"
            onClick={() => setExpanded(true)}
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="glass relative flex size-11 items-center justify-center rounded-full border shadow-lg transition-shadow hover:shadow-xl"
            title={t("todo.open")}
            aria-label={t("todo.open")}
          >
            <ListTodo className="size-5 text-primary" />
            {remaining > 0 && (
              <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] font-bold tabular-nums text-primary-foreground">
                {remaining}
              </span>
            )}
          </motion.button>
        )}
      </AnimatePresence>

      <TodoAddDialog open={pickerOpen} onOpenChange={setPickerOpen} />
    </>
  );
}

function TodoRow({ item }: { item: TodoItem }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const remove = useTodoStore((s) => s.remove);
  const setTopicStudied = useStudyStore((s) => s.setTopicStudied);

  return (
    <li className="group/todo flex items-center gap-2 rounded-lg px-1.5 py-1 transition-colors hover:bg-accent/50">
      <button
        type="button"
        onClick={() => void setTopicStudied(item.topic_id, !item.studied)}
        title={
          item.studied ? t("todo.markNotCompleted") : t("todo.markCompleted")
        }
        aria-label={
          item.studied ? t("todo.markNotCompleted") : t("todo.markCompleted")
        }
        className={cn(
          "grid size-4 shrink-0 place-items-center rounded-sm border transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          item.studied
            ? "border-success bg-success text-white"
            : "border-muted-foreground/40 hover:border-muted-foreground",
        )}
      >
        {item.studied && <Check className="size-3" strokeWidth={3} />}
      </button>
      <button
        type="button"
        onClick={() => navigate(`/documents/${item.document_id}/study/${item.topic_id}`)}
        className="min-w-0 flex-1 rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        title={t("todo.openTopic", { title: item.title })}
      >
        <span
          className={cn(
            "block truncate text-sm",
            item.studied && "text-muted-foreground line-through",
          )}
        >
          {item.title}
        </span>
        <span className="block truncate text-[11px] text-muted-foreground/80">
          {item.subject_name} · {item.chapter_title}
        </span>
      </button>
      <button
        type="button"
        onClick={() => void remove(item.topic_id)}
        title={t("todo.remove")}
        aria-label={t("todo.removeAria", { title: item.title })}
        className="shrink-0 rounded-md p-1 text-muted-foreground opacity-0 transition hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover/todo:opacity-100"
      >
        <X className="size-3.5" />
      </button>
    </li>
  );
}
