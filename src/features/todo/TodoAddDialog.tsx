import { Check, ListTodo, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { useCalendarStore } from "@/stores/calendar";
import { useTodoStore } from "@/stores/todo";
import type { CatalogSubject, CatalogTopic } from "@/types/calendar";

interface TodoAddDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface ChapterGroup {
  title: string;
  topics: CatalogTopic[];
}

interface DocGroup {
  id: number;
  filename: string;
  chapters: ChapterGroup[];
}

interface SubjectSection {
  subject: CatalogSubject;
  documents: DocGroup[];
}

/** Group a subject's flat (ordered) topic list into document → chapter runs. */
function groupTopics(topics: CatalogTopic[]): DocGroup[] {
  const documents: DocGroup[] = [];
  for (const topic of topics) {
    let doc = documents[documents.length - 1];
    if (!doc || doc.id !== topic.document_id) {
      doc = { id: topic.document_id, filename: topic.document_filename, chapters: [] };
      documents.push(doc);
    }
    let chapter = doc.chapters[doc.chapters.length - 1];
    if (!chapter || chapter.title !== topic.chapter_title) {
      chapter = { title: topic.chapter_title, topics: [] };
      doc.chapters.push(chapter);
    }
    chapter.topics.push(topic);
  }
  return documents;
}

/**
 * The to-do list's "+" picker: search across every subject's topics and pin any
 * selection to the list. Each document header has a select-all for "add all
 * topics of this deck" in one tap; topics already on the list are shown ticked
 * and can't be re-added (the server would skip them anyway).
 */
export function TodoAddDialog({ open, onOpenChange }: TodoAddDialogProps) {
  const { t } = useTranslation();
  const catalog = useCalendarStore((s) => s.catalog);
  const fetchCatalog = useCalendarStore((s) => s.fetchCatalog);
  const items = useTodoStore((s) => s.items);
  const addToList = useTodoStore((s) => s.add);

  const [query, setQuery] = useState("");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  // A fresh open reloads the catalog (studied flags move around) and resets.
  useEffect(() => {
    if (!open) return;
    setQuery("");
    setSelected(new Set());
    setBusy(false);
    setError(null);
    setLoading(true);
    void fetchCatalog(true).finally(() => setLoading(false));
  }, [open, fetchCatalog]);

  const onList = useMemo(
    () => new Set(items.map((i) => i.topic_id)),
    [items],
  );

  // Subject → document → chapter tree, pruned by the search query (which
  // matches the topic, chapter, document, and subject names).
  const sections = useMemo<SubjectSection[]>(() => {
    const q = query.trim().toLowerCase();
    return catalog
      .map((subject) => {
        const topics = q
          ? subject.topics.filter((topic) =>
              `${topic.title} ${topic.chapter_title} ${topic.document_filename} ${subject.name}`
                .toLowerCase()
                .includes(q),
            )
          : subject.topics;
        return { subject, documents: groupTopics(topics) };
      })
      .filter((section) => section.documents.length > 0);
  }, [catalog, query]);

  const visibleSelectable = useMemo(() => {
    const ids: number[] = [];
    for (const section of sections)
      for (const doc of section.documents)
        for (const chapter of doc.chapters)
          for (const topic of chapter.topics)
            if (!onList.has(topic.id)) ids.push(topic.id);
    return ids;
  }, [sections, onList]);

  function toggle(id: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleMany(ids: number[], on: boolean) {
    setSelected((prev) => {
      const next = new Set(prev);
      for (const id of ids) {
        if (on) next.add(id);
        else next.delete(id);
      }
      return next;
    });
  }

  async function submit() {
    if (selected.size === 0) return;
    setBusy(true);
    setError(null);
    try {
      await addToList([...selected]);
      onOpenChange(false);
    } catch {
      setError(t("todo.picker.addFailed"));
    } finally {
      setBusy(false);
    }
  }

  const empty = !loading && sections.length === 0;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-full max-w-2xl flex-col gap-0 overflow-hidden p-0">
        <DialogHeader className="border-b px-6 py-4 text-left">
          <DialogTitle className="flex items-center gap-2">
            <ListTodo className="size-4 text-primary" />
            {t("todo.picker.title")}
          </DialogTitle>
          <DialogDescription>{t("todo.picker.description")}</DialogDescription>
        </DialogHeader>

        {/* Search across all subjects/documents/topics. */}
        <div className="border-b bg-muted/30 px-6 py-3">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={t("todo.picker.searchPlaceholder")}
              className="pl-9"
              autoFocus
            />
          </div>
        </div>

        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-4">
          {loading && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {t("todo.picker.loading")}
            </p>
          )}
          {empty && (
            <p className="py-12 text-center text-sm text-muted-foreground">
              {query
                ? t("todo.picker.noMatches")
                : t("todo.picker.emptyCatalog")}
            </p>
          )}
          {!loading && (
            <div className="space-y-6">
              {sections.map(({ subject, documents }) => (
                <section key={subject.id}>
                  <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-primary">
                    {subject.name}
                  </p>
                  <div className="space-y-4">
                    {documents.map((doc) => {
                      const docSelectable = doc.chapters
                        .flatMap((chapter) => chapter.topics)
                        .filter((topic) => !onList.has(topic.id))
                        .map((topic) => topic.id);
                      const docAllOn =
                        docSelectable.length > 0 &&
                        docSelectable.every((id) => selected.has(id));
                      return (
                        <div key={doc.id}>
                          <div className="mb-1.5 flex items-center justify-between gap-2">
                            <span className="truncate text-sm font-semibold">
                              {doc.filename}
                            </span>
                            {docSelectable.length > 0 && (
                              <button
                                type="button"
                                onClick={() => toggleMany(docSelectable, !docAllOn)}
                                className="shrink-0 rounded-md px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                              >
                                {docAllOn
                                  ? t("todo.picker.clear")
                                  : t("todo.picker.selectAll")}
                              </button>
                            )}
                          </div>
                          <div className="space-y-3 border-l border-border/60 pl-3">
                            {doc.chapters.map((chapter) => (
                              <div key={chapter.title}>
                                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                                  {chapter.title}
                                </p>
                                <ul className="space-y-0.5">
                                  {chapter.topics.map((topic) => (
                                    <PickerRow
                                      key={topic.id}
                                      topic={topic}
                                      added={onList.has(topic.id)}
                                      checked={selected.has(topic.id)}
                                      onToggle={() => toggle(topic.id)}
                                    />
                                  ))}
                                </ul>
                              </div>
                            ))}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t px-6 py-3">
          <span className="text-xs tabular-nums text-muted-foreground">
            {error ? (
              <span className="text-destructive">{error}</span>
            ) : selected.size > 0 ? (
              t("todo.picker.selected", { count: selected.size })
            ) : visibleSelectable.length === 0 && !loading && !empty ? (
              t("todo.picker.allAdded")
            ) : (
              ""
            )}
          </span>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => onOpenChange(false)}>
              {t("todo.picker.cancel")}
            </Button>
            <Button
              size="sm"
              disabled={selected.size === 0 || busy}
              onClick={() => void submit()}
            >
              {busy
                ? t("todo.picker.adding")
                : selected.size === 0
                  ? t("todo.picker.addEmpty")
                  : t("todo.picker.add", { count: selected.size })}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

function PickerRow({
  topic,
  added,
  checked,
  onToggle,
}: {
  topic: CatalogTopic;
  added: boolean;
  checked: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation();
  return (
    <li>
      <button
        type="button"
        disabled={added}
        onClick={onToggle}
        title={added ? t("todo.picker.alreadyAdded") : undefined}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
          added ? "cursor-default text-muted-foreground/60" : "hover:bg-accent/60",
          checked && "bg-primary/5",
        )}
      >
        <span
          aria-hidden
          className={cn(
            "flex size-4 shrink-0 items-center justify-center rounded border transition-colors",
            checked || added
              ? "border-primary bg-primary text-primary-foreground"
              : "border-input bg-background",
            added && "opacity-50",
          )}
        >
          {(checked || added) && <Check className="size-3" strokeWidth={3} />}
        </span>
        <span className="min-w-0 flex-1 truncate">{topic.title}</span>
        {added && (
          <span className="shrink-0 text-xs text-muted-foreground/70">
            {t("todo.picker.onList")}
          </span>
        )}
        {!added && topic.studied && (
          <span className="shrink-0 text-xs text-success">
            {t("todo.picker.studiedBadge")}
          </span>
        )}
      </button>
    </li>
  );
}
