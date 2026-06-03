import { Maximize2, Minimize2 } from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { cn } from "@/lib/utils";
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
  // Exam-prep documents are assessment-only — no notes were generated, so the
  // Notes tab is dropped and the quiz leads.
  const isExam = mode === "exam";

  // The active tab is controlled so it survives the inline ↔ full-screen swap.
  const [tab, setTab] = useState<string>(isExam ? "quiz" : "notes");
  const [fullscreen, setFullscreen] = useState(false);

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
          <TabsList>
            {!isExam && <TabsTrigger value="notes">Notes</TabsTrigger>}
            <TabsTrigger value="quiz">
              Quiz{content.mcqs.length > 0 && ` (${content.mcqs.length})`}
            </TabsTrigger>
            <TabsTrigger value="flashcards">
              Flashcards{content.flashcards.length > 0 && ` (${content.flashcards.length})`}
            </TabsTrigger>
          </TabsList>
          {/* In normal view the toggle lives at the end of the tab row (the
              controls it affects); in full screen it becomes a floating pill. */}
          {!fullscreen && (
            <Button
              variant="ghost"
              size="icon"
              className="shrink-0 text-muted-foreground"
              onClick={() => setFullscreen(true)}
              title="Full screen"
              aria-label="Enter full screen"
            >
              <Maximize2 />
            </Button>
          )}
        </div>

        {!isExam && (
          <TabsContent value="notes">
            <NotesTab topicId={content.id} notes={content.notes} />
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
          title="Exit full screen (Esc)"
          aria-label="Exit full screen"
          className="glass fixed right-5 top-5 z-20 inline-flex items-center gap-2 rounded-full border px-3.5 py-2 text-sm font-medium text-muted-foreground shadow-sm transition-all hover:text-foreground hover:shadow-md active:scale-95"
        >
          <Minimize2 className="size-4" />
          <span className="hidden sm:inline">Esc</span>
        </button>
      )}
      <div
        className={cn(
          fullscreen &&
            "fullscreen-zoom animate-rise relative z-10 mx-auto max-w-3xl px-6 py-12 sm:py-16",
        )}
      >
        {body}
      </div>
    </div>
  );
}
