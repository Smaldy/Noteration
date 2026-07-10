import { CalendarPlus, Check, Maximize2, Minimize2 } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { AddToCalendarDialog } from "@/features/calendar/AddToCalendarDialog";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
import { useStudyStore } from "@/stores/study";
import type { DocumentMode } from "@/types/library";
import type { TopicContent } from "@/types/study";

import { FlashcardsTab } from "./FlashcardsTab";
import { NotesTab } from "./NotesTab";
import { QuizTab } from "./QuizTab";

export function TopicContentPanel({
  content,
  mode = "study",
}: {
  content: TopicContent;
  mode?: DocumentMode;
}) {
  const { t } = useTranslation();
  const setTopicStudied = useStudyStore((s) => s.setTopicStudied);
  // Exam-prep documents are assessment-only — no notes were generated, so the
  // Notes tab is dropped and the quiz leads.
  const isExam = mode === "exam";

  // The active tab is controlled so it survives the inline ↔ full-screen swap.
  const [tab, setTab] = useState<string>(isExam ? "quiz" : "notes");
  const [fullscreen, setFullscreen] = useState(false);
  const [addToCalendar, setAddToCalendar] = useState(false);

  // While full screen: Esc exits, and the page behind it is scroll-locked.
  useEffect(() => {
    if (!fullscreen) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setFullscreen(false);
    }
    window.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [fullscreen]);

  const body = (
    <>
      <h2
        className={cn(
          "mb-4 font-semibold tracking-tight",
          fullscreen ? "text-center text-2xl" : "text-xl",
        )}
      >
        {content.title}
      </h2>

      <Tabs value={tab} onValueChange={setTab}>
        <div
          className={cn(
            "flex items-center gap-2",
            fullscreen ? "justify-center" : "justify-between",
          )}
        >
          <div className="flex min-w-0 items-center gap-3">
            <TabsList>
              {!isExam && (
                <TabsTrigger value="notes">{t("study.tabs.notes")}</TabsTrigger>
              )}
              <TabsTrigger value="quiz">
                {t("study.tabs.quiz")}
                {content.mcqs.length > 0 && ` (${content.mcqs.length})`}
              </TabsTrigger>
              <TabsTrigger value="flashcards">
                {t("study.tabs.flashcards")}
                {content.flashcards.length > 0 && ` (${content.flashcards.length})`}
              </TabsTrigger>
            </TabsList>
            {/* The topic's completed checkmark — deliberately outside the
                TabsList so it reads as state, not a fourth tab. */}
            <button
              type="button"
              onClick={() => void setTopicStudied(content.id, !content.studied)}
              title={
                content.studied
                  ? t("study.notes.markNotCompleted")
                  : t("study.notes.markCompleted")
              }
              className={cn(
                "inline-flex shrink-0 items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95",
                content.studied
                  ? "border-success/40 bg-success/10 text-success"
                  : "text-muted-foreground hover:border-ring/40 hover:text-foreground",
              )}
            >
              <span
                aria-hidden
                className={cn(
                  "grid size-3.5 shrink-0 place-items-center rounded-sm border transition-colors",
                  content.studied
                    ? "border-success bg-success text-white"
                    : "border-current/50",
                )}
              >
                {content.studied && <Check className="size-2.5" strokeWidth={3} />}
              </span>
              {content.studied
                ? t("study.notes.completed")
                : t("study.notes.markCompleted")}
            </button>
          </div>
          {/* In normal view the controls live at the end of the tab row; in
              full screen the fullscreen toggle becomes a floating pill. */}
          {!fullscreen && (
            <div className="flex shrink-0 items-center gap-1">
              <Button
                variant="ghost"
                size="icon"
                className="text-muted-foreground"
                onClick={() => setAddToCalendar(true)}
                title={t("study.tabs.addToCalendar")}
                aria-label={t("study.tabs.addToCalendar")}
              >
                <CalendarPlus />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="text-muted-foreground"
                onClick={() => setFullscreen(true)}
                title={t("study.tabs.fullscreen")}
                aria-label={t("study.tabs.enterFullscreen")}
              >
                <Maximize2 />
              </Button>
            </div>
          )}
        </div>

        {!isExam && (
          <TabsContent value="notes">
            <NotesTab
              topicId={content.id}
              notes={content.notes}
              attachments={content.attachments}
              generatedBy={content.generated_by}
            />
          </TabsContent>
        )}
        <TabsContent value="quiz">
          <QuizTab topicId={content.id} mcqs={content.mcqs} fullscreen={fullscreen} />
        </TabsContent>
        <TabsContent value="flashcards">
          <FlashcardsTab
            topicId={content.id}
            flashcards={content.flashcards}
            fullscreen={fullscreen}
          />
        </TabsContent>
      </Tabs>
    </>
  );

  // Same subtree either way (so tab/quiz/flashcard progress is preserved when
  // toggling) — only the wrapper changes. In full screen it becomes a fixed
  // overlay, which naturally hides the sidebar and centers + zooms the content
  // floating on the ambient gradient backdrop.
  return (
    <div
      className={cn(
        fullscreen && "fixed inset-0 z-50 overflow-y-auto fullscreen-stage",
      )}
    >
      {fullscreen && (
        <button
          type="button"
          onClick={() => setFullscreen(false)}
          title={t("study.tabs.exitFullscreenEsc")}
          aria-label={t("study.tabs.exitFullscreen")}
          className="glass fixed right-5 top-5 z-20 inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium text-muted-foreground shadow-sm transition-all hover:text-foreground hover:shadow-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring active:scale-95"
        >
          <Minimize2 className="size-4" />
          <span className="hidden sm:inline">Esc</span>
        </button>
      )}
      <div
        className={cn(
          fullscreen &&
            "fullscreen-zoom animate-rise relative z-10 mx-auto max-w-[70rem] px-6 py-12 sm:py-16",
        )}
      >
        {body}
      </div>

      <AddToCalendarDialog
        open={addToCalendar}
        onOpenChange={setAddToCalendar}
        presetTopic={{ id: content.id, title: content.title }}
      />
    </div>
  );
}
