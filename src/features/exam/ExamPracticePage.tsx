import { ArrowLeft, GraduationCap } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FlashcardsTab } from "@/features/study/FlashcardsTab";
import { QuizTab } from "@/features/study/QuizTab";
import { ApiError, api } from "@/lib/api";
import type { AggregateAssessment, AssessmentScope } from "@/types/assessment";

const VALID_SCOPES: AssessmentScope[] = ["chapters", "documents", "subjects"];

// Combined practice for a whole chapter, deck (document), or subject — the pooled
// quiz + flashcards across all its topics. Reuses the study tabs (without
// per-topic "Generate more", which doesn't apply to a pooled deck).
export function ExamPracticePage() {
  const { scope, id } = useParams<{ scope: string; id: string }>();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const { t } = useTranslation();

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
      setError(t("exam.practice.invalidLink"));
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
        setError(err instanceof ApiError ? err.message : t("exam.practice.loadFailed"));
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
        {t("exam.practice.back")}
      </button>

      {status === "loading" && (
        <p className="py-20 text-center text-sm text-muted-foreground">
          {t("exam.practice.loading")}
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
            {t("exam.practice.scopePractice", {
              scope: t(`exam.practice.scope.${data.scope}`),
            })}
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{data.title}</h1>
          <p className="mt-1 text-sm text-muted-foreground">
            {t("exam.practice.questions", { count: data.mcqs.length })} ·{" "}
            {t("exam.practice.cards", { count: data.flashcards.length })} ·{" "}
            {t("exam.practice.topics", { count: data.topic_count })}
          </p>

          <div className="mt-6">
            <Tabs defaultValue={initialTab}>
              <TabsList>
                <TabsTrigger value="quiz">
                  {t("exam.quiz")}
                  {data.mcqs.length > 0 && ` (${data.mcqs.length})`}
                </TabsTrigger>
                <TabsTrigger value="flashcards">
                  {t("exam.flashcards")}
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
