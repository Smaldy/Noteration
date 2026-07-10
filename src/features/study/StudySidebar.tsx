import {
  closestCenter,
  DndContext,
  type DragEndEvent,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
} from "@dnd-kit/core";
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from "@dnd-kit/sortable";
import { CSS } from "@dnd-kit/utilities";
import {
  GitMerge,
  GripVertical,
  Layers,
  ListChecks,
  ListTodo,
  Trash2,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { cn } from "@/lib/utils";
import { useTodoStore } from "@/stores/todo";
import type { ChapterNode, DocumentTree, TopicNode } from "@/types/study";

import { TopicStatusIcon } from "./TopicStatusIcon";

type PracticeScope = "chapters" | "documents" | "subjects";
type PracticeTab = "quiz" | "flashcards";
type OnPractice = (scope: PracticeScope, id: number, tab: PracticeTab) => void;

interface StudySidebarProps {
  tree: DocumentTree;
  selectedTopicId: number | null;
  onSelectTopic: (topicId: number) => void;
  onDeleteTopic: (topicId: number, title: string) => void;
  /** Open the merge picker: fold this topic into another topic of the subject. */
  onMergeTopic?: (topicId: number, title: string) => void;
  onToggleBookmark: (topicId: number, bookmarked: boolean) => void;
  onReorderTopics: (chapterId: number, orderedIds: number[]) => void;
  /** Open a pooled quiz/flashcards deck for a scope (whole subject/deck/chapter). */
  onPractice?: OnPractice;
  /** Open the custom topic selector (pick any subset of the subject's topics). */
  onChooseTopics?: () => void;
}

/** The topic under an open right-click menu (fixed at the cursor position). */
interface TopicMenu {
  x: number;
  y: number;
  topicId: number;
}

export function StudySidebar(props: StudySidebarProps) {
  const { tree, onPractice, onChooseTopics } = props;
  const { t } = useTranslation();
  const addToTodo = useTodoStore((s) => s.add);
  const [menu, setMenu] = useState<TopicMenu | null>(null);

  // Any click, scroll, Escape, or a right-click elsewhere dismisses the menu.
  // The contextmenu listener is capture-phase so it runs before a topic's own
  // handler — right-clicking another topic closes this menu, then opens its own.
  useEffect(() => {
    if (!menu) return;
    const close = () => setMenu(null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") close();
    };
    window.addEventListener("click", close);
    window.addEventListener("contextmenu", close, true);
    window.addEventListener("scroll", close, true);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("click", close);
      window.removeEventListener("contextmenu", close, true);
      window.removeEventListener("scroll", close, true);
      window.removeEventListener("keydown", onKey);
    };
  }, [menu]);

  function onTopicContextMenu(event: React.MouseEvent, topicId: number) {
    event.preventDefault();
    setMenu({
      x: Math.min(event.clientX, window.innerWidth - 220),
      y: Math.min(event.clientY, window.innerHeight - 56),
      topicId,
    });
  }

  return (
    <nav className="space-y-4">
      {menu && (
        <div
          className="fixed z-50 min-w-48 rounded-lg border bg-popover p-1 text-popover-foreground shadow-md"
          style={{ left: menu.x, top: menu.y }}
          role="menu"
        >
          <button
            type="button"
            role="menuitem"
            onClick={() => {
              void addToTodo([menu.topicId]);
              setMenu(null);
            }}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-sm transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ListTodo className="size-4 text-primary" />
            {t("todo.addToList")}
          </button>
        </div>
      )}
      {onPractice && (
        <div className="space-y-3 rounded-xl border bg-card/60 p-3 shadow-sm">
          <p className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-primary">
            <Layers className="size-3.5" />
            {t("study.sidebar.combinedPractice")}
          </p>
          <div className="space-y-1">
            <PracticeRow
              label={t("study.sidebar.subject")}
              onQuiz={() => onPractice("subjects", tree.subject_id, "quiz")}
              onCards={() => onPractice("subjects", tree.subject_id, "flashcards")}
            />
            <PracticeRow
              label={t("study.sidebar.deck")}
              onQuiz={() => onPractice("documents", tree.document_id, "quiz")}
              onCards={() => onPractice("documents", tree.document_id, "flashcards")}
            />
          </div>
          {onChooseTopics && (
            <button
              type="button"
              onClick={onChooseTopics}
              className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-dashed border-primary/40 px-2 py-1.5 text-xs font-medium text-primary transition-colors hover:border-primary/60 hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            >
              <ListChecks className="size-3.5" />
              {t("study.sidebar.chooseTopics")}
            </button>
          )}
        </div>
      )}
      {tree.chapters.map((chapter) => (
        <ChapterGroup
          key={chapter.id}
          chapter={chapter}
          onTopicContextMenu={onTopicContextMenu}
          {...props}
        />
      ))}
    </nav>
  );
}

function PracticeRow({
  label,
  onQuiz,
  onCards,
}: {
  label: string;
  onQuiz: () => void;
  onCards: () => void;
}) {
  const { t } = useTranslation();
  return (
    <div className="flex items-center justify-between gap-2 rounded-md px-1 py-0.5">
      <span className="truncate text-sm font-medium">{label}</span>
      <span className="flex shrink-0 items-center gap-1">
        <button
          type="button"
          onClick={onQuiz}
          className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t("study.sidebar.quiz")}
        </button>
        <button
          type="button"
          onClick={onCards}
          className="rounded-md bg-primary/10 px-2 py-0.5 text-xs font-medium text-primary transition-colors hover:bg-primary/20 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        >
          {t("study.sidebar.cards")}
        </button>
      </span>
    </div>
  );
}

function ChapterGroup({
  chapter,
  selectedTopicId,
  onSelectTopic,
  onDeleteTopic,
  onMergeTopic,
  onToggleBookmark,
  onReorderTopics,
  onTopicContextMenu,
}: {
  chapter: ChapterNode;
  onTopicContextMenu: (event: React.MouseEvent, topicId: number) => void;
} & Omit<StudySidebarProps, "tree">) {
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = chapter.topics.findIndex((t) => t.id === active.id);
    const newIndex = chapter.topics.findIndex((t) => t.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(chapter.topics, oldIndex, newIndex);
    onReorderTopics(chapter.id, next.map((t) => t.id));
  }

  return (
    <div>
      <div className="flex items-center justify-between gap-2 px-2">
        <h3 className="truncate text-xs font-semibold uppercase tracking-wide text-muted-foreground">
          {chapter.title}
        </h3>
      </div>
      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={chapter.topics.map((t) => t.id)}
          strategy={verticalListSortingStrategy}
        >
          <ul className="mt-1">
            {chapter.topics.map((topic) => (
              <SortableTopic
                key={topic.id}
                topic={topic}
                active={topic.id === selectedTopicId}
                onSelect={() => onSelectTopic(topic.id)}
                onDelete={() => onDeleteTopic(topic.id, topic.title)}
                onMerge={
                  onMergeTopic
                    ? () => onMergeTopic(topic.id, topic.title)
                    : undefined
                }
                onToggleBookmark={(b) => onToggleBookmark(topic.id, b)}
                onContextMenu={(e) => onTopicContextMenu(e, topic.id)}
              />
            ))}
          </ul>
        </SortableContext>
      </DndContext>
    </div>
  );
}

function SortableTopic({
  topic,
  active,
  onSelect,
  onDelete,
  onMerge,
  onToggleBookmark,
  onContextMenu,
}: {
  topic: TopicNode;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onMerge?: () => void;
  onToggleBookmark: (bookmarked: boolean) => void;
  onContextMenu: (event: React.MouseEvent) => void;
}) {
  const { t } = useTranslation();
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: topic.id });
  const skipped = topic.priority === "skip";

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      onContextMenu={onContextMenu}
      className={cn(
        "group/topic flex items-center rounded-md transition-colors",
        active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
        isDragging && "z-10 bg-card shadow-md ring-1 ring-primary/30",
      )}
    >
      <button
        type="button"
        aria-label={t("study.sidebar.dragToReorder")}
        title={t("study.sidebar.dragToReorder")}
        className="shrink-0 cursor-grab touch-none rounded-md p-1 text-muted-foreground/40 opacity-0 transition hover:text-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:cursor-grabbing group-hover/topic:opacity-100"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-3.5" />
      </button>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 rounded-md py-1.5 pr-1 text-left text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          skipped && "text-muted-foreground",
        )}
      >
        <TopicStatusIcon status={topic.status} priority={topic.priority} />
        <span className="truncate">{topic.title}</span>
      </button>
      <div className="flex shrink-0 items-center pr-1">
        <BookmarkButton
          bookmarked={topic.bookmarked}
          label={topic.title}
          size="sm"
          onToggle={onToggleBookmark}
          className={cn(
            "transition-opacity",
            !topic.bookmarked &&
              "opacity-0 focus-visible:opacity-100 group-hover/topic:opacity-100",
          )}
        />
        {onMerge && (
          <button
            type="button"
            title={t("study.sidebar.mergeTopic")}
            aria-label={t("study.sidebar.mergeTopicAria", { title: topic.title })}
            onClick={onMerge}
            className="rounded-md p-1 text-muted-foreground opacity-0 transition hover:text-primary focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover/topic:opacity-100"
          >
            <GitMerge className="size-3.5" />
          </button>
        )}
        <button
          type="button"
          title={t("study.sidebar.deleteTopic")}
          aria-label={t("study.sidebar.deleteTopicAria", { title: topic.title })}
          onClick={onDelete}
          className="rounded-md p-1 text-muted-foreground opacity-0 transition hover:text-destructive focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover/topic:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  );
}
