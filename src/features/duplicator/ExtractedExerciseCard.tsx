import { MarkdownView } from "@/components/MarkdownView";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import type { ExtractedExercise } from "@/types/duplicator";

import { VariantsPanel } from "./VariantsPanel";
import { VizRouter } from "./renderers/VizRouter";

export function ExtractedExerciseCard({
  exercise,
  index,
  yearLevel,
}: {
  exercise: ExtractedExercise;
  index: number;
  yearLevel: number;
}) {
  return (
    <Card>
      <CardContent className="pt-5">
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <span className="text-xs font-semibold text-muted-foreground">
            #{index + 1}
          </span>
          <Badge variant="secondary">{exercise.topic}</Badge>
          {exercise.subtopic && (
            <Badge variant="outline">{exercise.subtopic}</Badge>
          )}
          {exercise.difficulty_signals.map((signal) => (
            <span
              key={signal}
              className="rounded-full bg-muted px-2 py-0.5 text-[10px] text-muted-foreground"
            >
              {signal}
            </span>
          ))}
        </div>

        <div className="text-sm">
          <MarkdownView>{exercise.raw_text}</MarkdownView>
        </div>

        <VizRouter viz={exercise.viz} />

        <VariantsPanel exercise={exercise} yearLevel={yearLevel} />
      </CardContent>
    </Card>
  );
}
