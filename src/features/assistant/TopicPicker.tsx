import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { TopicTreeSections } from "@/components/TopicTreeSections";
import { useSubjectTopicTree } from "@/lib/useSubjectTopicTree";
import { cn } from "@/lib/utils";
import type { ReferenceTopic } from "@/stores/assistant";
import { useSubjectsStore } from "@/stores/subjects";

interface TopicPickerProps {
  /** The host dialog's open flag: a fresh open starts from a clean pick. */
  open: boolean;
  value: ReferenceTopic | null;
  onChange: (topic: ReferenceTopic) => void;
}

/**
 * Subject select, then one of its study topics — the picker shared by the
 * assistant's two topic flows (save a reply as a note, pin a reference topic).
 * Scoped to study documents: those are the ones carrying notes.
 */
export function TopicPicker({ open, value, onChange }: TopicPickerProps) {
  const { t } = useTranslation();
  const { subjects, loaded, fetchSubjects } = useSubjectsStore();
  const [subjectId, setSubjectId] = useState<number | null>(null);

  useEffect(() => {
    if (!open) return;
    setSubjectId(null);
    void fetchSubjects();
  }, [open, fetchSubjects]);

  const { tree, status, error } = useSubjectTopicTree(
    subjectId ?? Number.NaN,
    open && subjectId !== null,
    t("assistant.topicPicker.loadFailed"),
    "study",
  );
  const hasTopics = (tree?.documents ?? []).some((doc) =>
    doc.chapters.some((chapter) => chapter.topics.length > 0),
  );

  if (loaded && subjects.length === 0) {
    return (
      <p className="py-8 text-center text-sm text-muted-foreground">
        {t("assistant.topicPicker.noSubjects")}
      </p>
    );
  }

  return (
    <>
      <label className="block space-y-1.5">
        <span className="text-sm font-medium">
          {t("assistant.topicPicker.subjectLabel")}
        </span>
        <Select
          value={subjectId === null ? "" : String(subjectId)}
          onValueChange={(v) => setSubjectId(Number(v))}
        >
          <SelectTrigger className="w-full">
            <SelectValue
              placeholder={t("assistant.topicPicker.subjectPlaceholder")}
            />
          </SelectTrigger>
          <SelectContent>
            {subjects.map((s) => (
              <SelectItem key={s.id} value={String(s.id)}>
                {s.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </label>

      {subjectId !== null && status === "loading" && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t("common.loading")}
        </p>
      )}
      {subjectId !== null && status === "error" && (
        <p className="py-8 text-center text-sm text-destructive">{error}</p>
      )}
      {subjectId !== null && status === "loaded" && !hasTopics && (
        <p className="py-8 text-center text-sm text-muted-foreground">
          {t("assistant.topicPicker.noTopics")}
        </p>
      )}
      {subjectId !== null && status === "loaded" && hasTopics && (
        <div className="space-y-5">
          <TopicTreeSections
            documents={tree?.documents ?? []}
            renderTopic={(topic) => (
              <li key={topic.id}>
                <button
                  type="button"
                  onClick={() => onChange({ id: topic.id, title: topic.title })}
                  className={cn(
                    "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5 text-left text-sm transition-colors hover:bg-accent/60",
                    value?.id === topic.id && "bg-primary/10 font-medium text-primary",
                  )}
                >
                  <span
                    aria-hidden
                    className={cn(
                      "size-3.5 shrink-0 rounded-full border-2 transition-colors",
                      value?.id === topic.id
                        ? "border-primary bg-primary"
                        : "border-input",
                    )}
                  />
                  <span className="min-w-0 flex-1 truncate">{topic.title}</span>
                </button>
              </li>
            )}
          />
        </div>
      )}
    </>
  );
}
