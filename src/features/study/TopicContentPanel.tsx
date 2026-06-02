import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
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

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold tracking-tight">
        {content.title}
      </h2>
      <Tabs defaultValue={isExam ? "quiz" : "notes"}>
        <TabsList>
          {!isExam && <TabsTrigger value="notes">Notes</TabsTrigger>}
          <TabsTrigger value="quiz">
            Quiz{content.mcqs.length > 0 && ` (${content.mcqs.length})`}
          </TabsTrigger>
          <TabsTrigger value="flashcards">
            Flashcards{content.flashcards.length > 0 && ` (${content.flashcards.length})`}
          </TabsTrigger>
        </TabsList>
        {!isExam && (
          <TabsContent value="notes">
            <NotesTab topicId={content.id} notes={content.notes} />
          </TabsContent>
        )}
        <TabsContent value="quiz">
          <QuizTab topicId={content.id} mcqs={content.mcqs} />
        </TabsContent>
        <TabsContent value="flashcards">
          <FlashcardsTab topicId={content.id} flashcards={content.flashcards} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
