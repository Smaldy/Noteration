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
import { GripVertical, Trash2 } from "lucide-react";

import { BookmarkButton } from "@/features/bookmarks/BookmarkButton";
import { cn } from "@/lib/utils";
import type { ChapterNode, DocumentTree, TopicNode } from "@/types/study";

import { TopicStatusIcon } from "./TopicStatusIcon";

interface StudySidebarProps {
  tree: DocumentTree;
  selectedTopicId: number | null;
  onSelectTopic: (topicId: number) => void;
  onDeleteTopic: (topicId: number, title: string) => void;
  onToggleBookmark: (topicId: number, bookmarked: boolean) => void;
  onReorderTopics: (chapterId: number, orderedIds: number[]) => void;
}

export function StudySidebar(props: StudySidebarProps) {
  return (
    <nav className="space-y-4">
      {props.tree.chapters.map((chapter) => (
        <ChapterGroup key={chapter.id} chapter={chapter} {...props} />
      ))}
    </nav>
  );
}

function ChapterGroup({
  chapter,
  selectedTopicId,
  onSelectTopic,
  onDeleteTopic,
  onToggleBookmark,
  onReorderTopics,
}: { chapter: ChapterNode } & Omit<StudySidebarProps, "tree">) {
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
      <h3 className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        {chapter.title}
      </h3>
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
                onToggleBookmark={(b) => onToggleBookmark(topic.id, b)}
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
  onToggleBookmark,
}: {
  topic: TopicNode;
  active: boolean;
  onSelect: () => void;
  onDelete: () => void;
  onToggleBookmark: (bookmarked: boolean) => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } =
    useSortable({ id: topic.id });
  const skipped = topic.priority === "skip";

  return (
    <li
      ref={setNodeRef}
      style={{ transform: CSS.Transform.toString(transform), transition }}
      className={cn(
        "group/topic flex items-center rounded-md transition-colors",
        active ? "bg-accent text-accent-foreground" : "hover:bg-accent/50",
        isDragging && "z-10 bg-card shadow-md ring-1 ring-primary/30",
      )}
    >
      <button
        type="button"
        aria-label="Drag to reorder"
        title="Drag to reorder"
        className="shrink-0 cursor-grab touch-none rounded p-1 text-muted-foreground/40 opacity-0 transition hover:text-foreground focus-visible:opacity-100 active:cursor-grabbing group-hover/topic:opacity-100"
        {...attributes}
        {...listeners}
      >
        <GripVertical className="size-3.5" />
      </button>
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex min-w-0 flex-1 items-center gap-2 py-1.5 pr-1 text-left text-sm",
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
        <button
          type="button"
          title="Delete topic"
          aria-label={`Delete topic ${topic.title}`}
          onClick={onDelete}
          className="rounded p-1 text-muted-foreground opacity-0 transition hover:text-destructive focus-visible:opacity-100 group-hover/topic:opacity-100"
        >
          <Trash2 className="size-3.5" />
        </button>
      </div>
    </li>
  );
}
