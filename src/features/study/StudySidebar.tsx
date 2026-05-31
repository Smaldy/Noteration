import { Trash2 } from "lucide-react";

import { cn } from "@/lib/utils";
import type { DocumentTree } from "@/types/study";

import { TopicStatusIcon } from "./TopicStatusIcon";

interface StudySidebarProps {
  tree: DocumentTree;
  selectedTopicId: number | null;
  onSelectTopic: (topicId: number) => void;
  onDeleteTopic: (topicId: number, title: string) => void;
}

export function StudySidebar({
  tree,
  selectedTopicId,
  onSelectTopic,
  onDeleteTopic,
}: StudySidebarProps) {
  return (
    <nav className="space-y-4">
      {tree.chapters.map((chapter) => (
        <div key={chapter.id}>
          <h3 className="px-2 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
            {chapter.title}
          </h3>
          <ul className="mt-1">
            {chapter.topics.map((topic) => {
              const active = topic.id === selectedTopicId;
              const skipped = topic.priority === "skip";
              return (
                <li key={topic.id} className="group/topic relative">
                  <button
                    type="button"
                    onClick={() => onSelectTopic(topic.id)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md py-1.5 pl-2 pr-8 text-left text-sm transition-colors",
                      active
                        ? "bg-accent text-accent-foreground"
                        : "hover:bg-accent/50",
                      skipped && "text-muted-foreground",
                    )}
                  >
                    <TopicStatusIcon
                      status={topic.status}
                      priority={topic.priority}
                    />
                    <span className="truncate">{topic.title}</span>
                  </button>
                  <button
                    type="button"
                    title="Delete topic"
                    aria-label={`Delete topic ${topic.title}`}
                    onClick={() => onDeleteTopic(topic.id, topic.title)}
                    className="absolute right-1 top-1/2 -translate-y-1/2 rounded p-1 text-muted-foreground opacity-0 transition hover:text-destructive focus-visible:opacity-100 group-hover/topic:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
