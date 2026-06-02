import { ArrowLeft, GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FlashcardsTab } from "@/features/study/FlashcardsTab";
import { QuizTab } from "@/features/study/QuizTab";
import { ApiError, api } from "@/lib/api";
import type { AggregateAssessment, AssessmentScope } from "@/types/assessment";

const VALID_SCOPES: AssessmentScope[] = ["chapters", "documents", "subjects"];

const SCOPE_LABEL: Record<AggregateAssessment["scope"], string> = {
  chapter: "Argument",
  document: "Deck",
  subject: "Subject",
};

// Combined practice for a whole argument (chapter), deck (document), or subject —
// the pooled quiz + flashcards across all its topics. Reuses the study tabs
// (without per-topic "Generate more", which doesn't apply to a pooled deck).
export function ExamPracticePage() {
  const { scope, id } = useParams<{ scope: string; id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [data, setData] = useState<AggregateAssessment | null>(null);
  const [status, setStatus] = useState<"loading" | "loaded" | "error">("loading");
  const [error, setError] = useState<string | null>(null);

  const numericId = Number(id);
  const validScope = VALID_SCOPES.includes(scope as AssessmentScope);
  // Pool only exam material for a whole subject (study docs live in the Library).
  const query = scope === "subjects" ? "?mode=exam" : "";

  useEffect(() => {
    let cancelled = false;
    if (!validScope || !Number.isFinite(numericId)) {
      setStatus("error");
      setError("Invalid practice link.");
      return;
    }
    setStatus("loading");
    api
      .get<AggregateAssessment>(`/assessment/${scope}/${numericId}${query}`)
      .then((res) => {
        if (cancelled) return;
        setData(res);
        setStatus("loaded");
      })
      .catch((err) => {
        if (cancelled) return;
        setError(err instanceof ApiError ? err.message : "Failed to load practice.");
        setStatus("error");
      });
    return () => {
      cancelled = true;
    };
  }, [scope, numericId, query, validScope]);

  const initialTab = searchParams.get("tab") === "flashcards" ? "flashcards" : "quiz";

  return (
    <div className="mx-auto max-w-3xl px-6 py-10">
      <button
        type="button"
        onClick={() => navigate(-1)}
        className="mb-4 inline-flex items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="size-4" />
        Back
      </button>

      {status === "loading" && (
        <p className="py-20 text-center text-sm text-muted-foreground">
          Loading practice…
        </p>
      )}

      {status === "error" && (
        <div className="rounded-lg border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {status === "loaded" && data && (
        <>
          <div className="mb-1 flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-primary">
            <GraduationCap className="size-4" />
            {SCOPE_LABEL[data.scope]} practice
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {data.mcqs.length} question{data.mcqs.length === 1 ? "" : "s"} ·{" "}
            {data.flashcards.length} flashcard{data.flashcards.length === 1 ? "" : "s"}{" "}
            · {data.topic_count} topic{data.topic_count === 1 ? "" : "s"}
          </p>

          <div className="mt-6">
            <Tabs defaultValue={initialTab}>
              <TabsList>
                <TabsTrigger value="quiz">
                  Quiz{data.mcqs.length > 0 && ` (${data.mcqs.length})`}
                </TabsTrigger>
                <TabsTrigger value="flashcards">
                  Flashcards
                  {data.flashcards.length > 0 && ` (${data.flashcards.length})`}
                </TabsTrigger>
              </TabsList>
              <TabsContent value="quiz">
                <QuizTab mcqs={data.mcqs} />
              </TabsContent>
              <TabsContent value="flashcards">
                <FlashcardsTab flashcards={data.flashcards} />
              </TabsContent>
            </Tabs>
          </div>
        </>
      )}
    </div>
  );
}
