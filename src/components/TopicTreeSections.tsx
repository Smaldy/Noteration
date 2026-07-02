import type { ReactNode } from "react";

import type {
  SelectableDocument,
  SelectableTopic,
} from "@/types/assessment";

interface TopicTreeSectionsProps {
  documents: SelectableDocument[];
  /** Keep only these topics; chapters and documents left empty are dropped. */
  topicFilter?: (topic: SelectableTopic) => boolean;
  /** Rendered next to the filename (badges). */
  documentBadge?: (doc: SelectableDocument) => ReactNode;
  /** Rendered at the far right of the document header (bulk actions). */
  documentAction?: (doc: SelectableDocument) => ReactNode;
  /** One row per topic; must set a `key` on the returned element. */
  renderTopic: (topic: SelectableTopic) => ReactNode;
}

/**
 * The document → chapter → topic scaffolding shared by the subject-tree pickers
 * (custom practice selector, merge-target picker): a section per document with
 * a header row, chapters down a left border, and caller-rendered topic rows.
 */
export function TopicTreeSections({
  documents,
  topicFilter,
  documentBadge,
  documentAction,
  renderTopic,
}: TopicTreeSectionsProps) {
  return (
    <>
      {documents.map((doc) => {
        const chapters = doc.chapters
          .map((chapter) => ({
            chapter,
            topics: topicFilter
              ? chapter.topics.filter(topicFilter)
              : chapter.topics,
          }))
          .filter(({ topics }) => topics.length > 0);
        if (chapters.length === 0) return null;
        return (
          <section key={doc.id}>
            <div className="mb-2 flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <span className="truncate text-sm font-semibold">
                  {doc.filename}
                </span>
                {documentBadge?.(doc)}
              </div>
              {documentAction?.(doc)}
            </div>
            <div className="space-y-3 border-l border-border/60 pl-3">
              {chapters.map(({ chapter, topics }) => (
                <div key={chapter.id}>
                  <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    {chapter.title}
                  </p>
                  <ul className="space-y-0.5">{topics.map(renderTopic)}</ul>
                </div>
              ))}
            </div>
          </section>
        );
      })}
    </>
  );
}
