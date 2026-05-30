import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import type { TopicContent } from "@/types/study";

import { FlashcardsTab } from "./FlashcardsTab";
import { NotesTab } from "./NotesTab";
import { QuizTab } from "./QuizTab";

export function TopicContentPanel({ content }: { content: TopicContent }) {
  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold tracking-tight">
        {content.title}
      </h2>
      <Tabs defaultValue="notes">
        <TabsList>
          <TabsTrigger value="notes">Notes</TabsTrigger>
          <TabsTrigger value="quiz">
            Quiz{content.mcqs.length > 0 && ` (${content.mcqs.length})`}
          </TabsTrigger>
          <TabsTrigger value="flashcards">
            Flashcards{content.flashcards.length > 0 && ` (${content.flashcards.length})`}
          </TabsTrigger>
        </TabsList>
        <TabsContent value="notes">
          <NotesTab notes={content.notes} />
        </TabsContent>
        <TabsContent value="quiz">
          <QuizTab mcqs={content.mcqs} />
        </TabsContent>
        <TabsContent value="flashcards">
          <FlashcardsTab flashcards={content.flashcards} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
