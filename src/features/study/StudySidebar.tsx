import { cn } from "@/lib/utils";
import type { DocumentTree } from "@/types/study";

import { TopicStatusIcon } from "./TopicStatusIcon";

interface StudySidebarProps {
  tree: DocumentTree;
  selectedTopicId: number | null;
  onSelectTopic: (topicId: number) => void;
}

export function StudySidebar({
  tree,
  selectedTopicId,
  onSelectTopic,
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
                <li key={topic.id}>
                  <button
                    type="button"
                    onClick={() => onSelectTopic(topic.id)}
                    className={cn(
                      "flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm transition-colors",
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
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}
