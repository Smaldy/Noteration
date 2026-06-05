import { ArrowLeft } from "lucide-react";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";

import { useStudyStore } from "@/stores/study";

import { StudySidebar } from "./StudySidebar";
import { TopicContentPanel } from "./TopicContentPanel";

export function StudyPage() {
  const { id, topicId } = useParams<{ id: string; topicId?: string }>();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const documentId = Number(id);
  const selectedTopicId = topicId ? Number(topicId) : null;

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
            onToggleBookmark={(tId, b) => void toggleTopicBookmark(tId, b)}
            onReorderTopics={(chapterId, ids) => void reorderTopics(chapterId, ids)}
            onPractice={
              tree.mode === "exam"
                ? (scope, practiceId, tab) =>
                    navigate(`/exam/practice/${scope}/${practiceId}?tab=${tab}`)
                : undefined
            }
          />
        )}
      </aside>

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
