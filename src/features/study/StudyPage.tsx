import { ArrowLeft } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { TopicSelectDialog } from "@/features/practice/TopicSelectDialog";
import { useStudyStore } from "@/stores/study";

import { MergeTopicDialog } from "./MergeTopicDialog";
import { StudySidebar } from "./StudySidebar";
import { TopicContentPanel } from "./TopicContentPanel";

export function StudyPage() {
  const { id, topicId } = useParams<{ id: string; topicId?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const documentId = Number(id);
  const selectedTopicId = topicId ? Number(topicId) : null;
  const [selectorOpen, setSelectorOpen] = useState(false);
  const [mergeSource, setMergeSource] = useState<{
    id: number;
    title: string;
  } | null>(null);

  const {
    tree,
    treeStatus,
    treeError,
    content,
    contentStatus,
    contentError,
    fetchTree,
    fetchTopic,
    deleteTopic,
    mergeTopic,
    toggleTopicBookmark,
    reorderTopics,
    clearContent,
  } = useStudyStore();

  useEffect(() => {
    if (Number.isFinite(documentId)) void fetchTree(documentId);
  }, [documentId, fetchTree]);

  useEffect(() => {
    if (selectedTopicId !== null) void fetchTopic(selectedTopicId);
    else clearContent();
  }, [selectedTopicId, fetchTopic, clearContent]);

  function selectTopic(nextTopicId: number) {
    navigate(`/documents/${documentId}/study/${nextTopicId}`);
  }

  async function handleMerge(targetId: number, consolidate: boolean) {
    const sourceId = mergeSource?.id ?? null;
    if (sourceId === null) return;
    await mergeTopic(sourceId, targetId, consolidate, documentId);
    setMergeSource(null);
    // The folded topic is gone; follow its content to the merge target when it
    // was the open topic (the target may live in another document — the tree
    // lookup below only finds same-document targets, so fall back home).
    if (sourceId !== selectedTopicId) return;
    const { tree: nextTree } = useStudyStore.getState();
    const inThisDoc = nextTree?.chapters.some((chapter) =>
      chapter.topics.some((topic) => topic.id === targetId),
    );
    navigate(
      inThisDoc
        ? `/documents/${documentId}/study/${targetId}`
        : `/documents/${documentId}/study`,
    );
  }

  async function handleDeleteTopic(deleteId: number, title: string) {
    const ok = window.confirm(t("study.deleteTopicConfirm", { title }));
    if (!ok) return;
    try {
      await deleteTopic(deleteId, documentId);
      // If the open topic was the one removed, drop back to the empty state.
      if (deleteId === selectedTopicId) {
        navigate(`/documents/${documentId}/study`);
      }
    } catch {
      window.alert(t("study.deleteTopicFailed"));
    }
  }

  return (
    <div className="mx-auto flex max-w-6xl gap-6 px-6 py-8">
      <aside className="w-64 shrink-0">
        <button
          type="button"
          onClick={() => navigate("/")}
          className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          {t("common.library")}
        </button>

        {treeStatus === "loading" && (
          <p className="px-2 text-sm text-muted-foreground">{t("common.loading")}</p>
        )}
        {treeStatus === "error" && (
          <p className="px-2 text-sm text-destructive">{treeError}</p>
        )}
        {treeStatus === "loaded" && tree && (
          <StudySidebar
            tree={tree}
            selectedTopicId={selectedTopicId}
            onSelectTopic={selectTopic}
            onDeleteTopic={handleDeleteTopic}
            onMergeTopic={(topicId, title) => setMergeSource({ id: topicId, title })}
            onToggleBookmark={(tId, b) => void toggleTopicBookmark(tId, b)}
            onReorderTopics={(chapterId, ids) => void reorderTopics(chapterId, ids)}
            onPractice={(scope, practiceId, tab) =>
              navigate(
                `/exam/practice/${scope}/${practiceId}?tab=${tab}&mode=${tree.mode}`,
              )
            }
            onChooseTopics={() => setSelectorOpen(true)}
          />
        )}
      </aside>

      {treeStatus === "loaded" && tree && (
        <TopicSelectDialog
          open={selectorOpen}
          onOpenChange={setSelectorOpen}
          subjectId={tree.subject_id}
          mode={tree.mode}
        />
      )}

      {treeStatus === "loaded" && tree && mergeSource && (
        <MergeTopicDialog
          open
          onOpenChange={(open) => {
            if (!open) setMergeSource(null);
          }}
          subjectId={tree.subject_id}
          sourceTopicId={mergeSource.id}
          sourceTopicTitle={mergeSource.title}
          onMerge={handleMerge}
        />
      )}

      <main className="min-w-0 flex-1">
        {selectedTopicId === null && (
          <p className="py-20 text-center text-sm text-muted-foreground">
            {t("study.selectTopic")}
          </p>
        )}
        {selectedTopicId !== null && contentStatus === "loading" && (
          <p className="py-20 text-center text-sm text-muted-foreground">
            {t("study.loadingTopic")}
          </p>
        )}
        {selectedTopicId !== null && contentStatus === "error" && (
          <p className="py-20 text-center text-sm text-destructive">
            {contentError}
          </p>
        )}
        {selectedTopicId !== null &&
          contentStatus === "loaded" &&
          content &&
          content.id === selectedTopicId && (
            <TopicContentPanel content={content} mode={tree?.mode} />
          )}
      </main>
    </div>
  );
}
