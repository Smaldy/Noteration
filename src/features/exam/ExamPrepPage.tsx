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
  rectSortingStrategy,
  SortableContext,
  sortableKeyboardCoordinates,
} from "@dnd-kit/sortable";
import {
  GraduationCap,
  Layers,
  ListChecks,
  Plus,
  Sparkles,
} from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { BackLink, EmptyState, PageHeader, PageShell } from "@/components/PageShell";
import { Button } from "@/components/ui/button";
import { DocumentCard } from "@/features/library/DocumentCard";
import { TopicSelectDialog } from "@/features/practice/TopicSelectDialog";
import { UploadDialog } from "@/features/upload/UploadDialog";
import { useExamStore } from "@/stores/library";

import type { DocumentSummary } from "@/types/library";

interface SubjectGroup {
  subjectId: number;
  subjectName: string;
  docs: DocumentSummary[];
}

function groupBySubject(docs: DocumentSummary[]): SubjectGroup[] {
  const groups: SubjectGroup[] = [];
  const byId = new Map<number, SubjectGroup>();
  for (const doc of docs) {
    let group = byId.get(doc.subject_id);
    if (!group) {
      group = {
        subjectId: doc.subject_id,
        subjectName: doc.subject_name,
        docs: [],
      };
      byId.set(doc.subject_id, group);
      groups.push(group);
    }
    group.docs.push(doc);
  }
  return groups;
}

// The Exam Prep section: documents are assessment-only (MCQs + flashcards, no
// notes), grouped by subject. Each subject and each deck exposes a combined
// quiz/flashcards practice (pooled across topics).
export function ExamPrepPage() {
  const {
    documents,
    status,
    error,
    fetchDocuments,
    deleteDocument,
    reorderDocuments,
    toggleSubjectBookmark,
  } = useExamStore();
  const [uploadOpen, setUploadOpen] = useState(false);
  const navigate = useNavigate();
  const { t } = useTranslation();

  useEffect(() => {
    void fetchDocuments();
  }, [fetchDocuments]);

  async function handleDelete(doc: DocumentSummary) {
    const ok = window.confirm(t("exam.deleteConfirm", { name: doc.filename }));
    if (!ok) return;
    try {
      await deleteDocument(doc.id);
    } catch {
      window.alert(t("exam.deleteFailed"));
    }
  }

  const groups = groupBySubject(documents);

  return (
    <PageShell>
      <BackLink />
      <PageHeader
        icon={<GraduationCap className="size-7 text-primary" />}
        title={t("exam.title")}
        subtitle={t("exam.subtitle")}
        actions={
          <>
            <Button variant="outline" onClick={() => navigate("/duplicator")}>
              <Sparkles />
              {t("nav.duplicator")}
            </Button>
            <Button onClick={() => setUploadOpen(true)}>
              <Plus />
              {t("exam.addPdf")}
            </Button>
          </>
        }
      />

      <UploadDialog
        open={uploadOpen}
        onOpenChange={setUploadOpen}
        store={useExamStore}
        exam
        onUploaded={(documentId) =>
          navigate(`/documents/${documentId}/review?from=exam`)
        }
      />

      {status === "loading" && (
        <p className="text-sm text-muted-foreground">{t("exam.loading")}</p>
      )}

      {status === "error" && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          <p>{error}</p>
          <Button
            variant="outline"
            size="sm"
            className="mt-3"
            onClick={() => void fetchDocuments()}
          >
            {t("common.retry")}
          </Button>
        </div>
      )}

      {status === "loaded" && documents.length === 0 && (
        <EmptyState
          icon={GraduationCap}
          title={t("exam.emptyTitle")}
          description={t("exam.emptyDesc")}
          action={
            <Button onClick={() => setUploadOpen(true)}>
              <Plus />
              {t("exam.addPdf")}
            </Button>
          }
        />
      )}

      {status === "loaded" && groups.length > 0 && (
        <div className="space-y-8">
          {groups.map((group) => (
            <SubjectSection
              key={group.subjectId}
              group={group}
              onDelete={handleDelete}
              onToggleBookmark={(subjectId, bookmarked) =>
                void toggleSubjectBookmark(subjectId, bookmarked)
              }
              onReorder={(ids) => void reorderDocuments(ids)}
            />
          ))}
        </div>
      )}
    </PageShell>
  );
}

function SubjectSection({
  group,
  onDelete,
  onToggleBookmark,
  onReorder,
}: {
  group: SubjectGroup;
  onDelete: (doc: DocumentSummary) => void;
  onToggleBookmark: (subjectId: number, bookmarked: boolean) => void;
  onReorder: (ids: number[]) => void;
}) {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [selectorOpen, setSelectorOpen] = useState(false);
  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 6 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates }),
  );

  function handleDragEnd(event: DragEndEvent) {
    const { active, over } = event;
    if (!over || active.id === over.id) return;
    const oldIndex = group.docs.findIndex((d) => d.id === active.id);
    const newIndex = group.docs.findIndex((d) => d.id === over.id);
    if (oldIndex < 0 || newIndex < 0) return;
    const next = arrayMove(group.docs, oldIndex, newIndex);
    onReorder(next.map((d) => d.id));
  }

  return (
    <section>
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3 border-b pb-2">
        <h2 className="truncate text-lg font-semibold tracking-tight">
          {group.subjectName}
        </h2>
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => setSelectorOpen(true)}
            className="flex items-center gap-1.5 rounded-md px-1.5 py-0.5 text-xs font-medium text-primary hover:bg-primary/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          >
            <ListChecks className="size-3.5" />
            {t("exam.chooseTopics")}
          </button>
          <PracticeButtons
            label={t("exam.wholeSubject")}
            onQuiz={() =>
              navigate(`/exam/practice/subjects/${group.subjectId}?tab=quiz&mode=exam`)
            }
            onCards={() =>
              navigate(
                `/exam/practice/subjects/${group.subjectId}?tab=flashcards&mode=exam`,
              )
            }
          />
        </div>
      </div>

      <TopicSelectDialog
        open={selectorOpen}
        onOpenChange={setSelectorOpen}
        subjectId={group.subjectId}
        mode="exam"
      />

      <DndContext
        sensors={sensors}
        collisionDetection={closestCenter}
        onDragEnd={handleDragEnd}
      >
        <SortableContext
          items={group.docs.map((d) => d.id)}
          strategy={rectSortingStrategy}
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {group.docs.map((doc) => (
              <DocumentCard
                key={doc.id}
                doc={doc}
                onDelete={onDelete}
                onToggleBookmark={onToggleBookmark}
                actions={
                  doc.status === "ready" || doc.topics_ready > 0 ? (
                    <PracticeButtons
                      label={t("exam.thisDeck")}
                      onQuiz={() =>
                        navigate(`/exam/practice/documents/${doc.id}?tab=quiz`)
                      }
                      onCards={() =>
                        navigate(`/exam/practice/documents/${doc.id}?tab=flashcards`)
                      }
                    />
                  ) : undefined
                }
              />
            ))}
          </div>
        </SortableContext>
      </DndContext>
    </section>
  );
}

function PracticeButtons({
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
    <div className="flex shrink-0 items-center gap-1.5 text-xs">
      <Layers className="size-3.5 text-muted-foreground" />
      <span className="mr-1 hidden text-muted-foreground sm:inline">{label}:</span>
      <Button variant="outline" size="sm" className="h-7 px-2" onClick={onQuiz}>
        {t("exam.quiz")}
      </Button>
      <Button variant="outline" size="sm" className="h-7 px-2" onClick={onCards}>
        {t("exam.flashcards")}
      </Button>
    </div>
  );
}
