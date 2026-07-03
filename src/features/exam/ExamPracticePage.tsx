import { GraduationCap } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";

import { BackLink, PageShell } from "@/components/PageShell";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { FlashcardsTab } from "@/features/study/FlashcardsTab";
import { QuizTab } from "@/features/study/QuizTab";
import { ApiError, api } from "@/lib/api";
import type { AggregateAssessment, AssessmentScope } from "@/types/assessment";

const VALID_SCOPES: AssessmentScope[] = [
  "chapters",
  "documents",
  "subjects",
  "topics",
];

// Combined practice for a whole chapter, deck (document), subject, or an explicit
// set of chosen topics — the pooled quiz + flashcards across them. Reuses the
// study tabs (without per-topic "Generate more", which doesn't apply to a pool).
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
  // A custom selection carries its topic ids in `?ids=1,2,3`; whole-subject pools
  // are scoped to a section via `?mode=study|exam` (study docs live in the Library,
  // exam decks in Exam Prep). Chapter/document scopes need neither.
  const idsParam = searchParams.get("ids") ?? "";
  const modeParam = searchParams.get("mode");

  // The assessment endpoint to call for this scope.
  const requestPath = useMemo<string | null>(() => {
    if (!validScope) return null;
    if (scope === "topics") {
      const ids = idsParam
        .split(",")
        .map((part) => Number(part))
        .filter((value) => Number.isFinite(value) && value > 0);
      if (ids.length === 0) return null;
      const qs = ids.map((value) => `topic_id=${value}`).join("&");
      return `/assessment/topics?${qs}`;
    }
    if (!Number.isFinite(numericId)) return null;
    const query = scope === "subjects" && modeParam ? `?mode=${modeParam}` : "";
    return `/assessment/${scope}/${numericId}${query}`;
  }, [validScope, scope, idsParam, numericId, modeParam]);

  useEffect(() => {
    let cancelled = false;
    if (requestPath === null) {
      setStatus("error");
      setError(t("exam.practice.invalidLink"));
      return;
    }
    setStatus("loading");
    api
      .get<AggregateAssessment>(requestPath)
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
  }, [requestPath, t]);

  const initialTab = searchParams.get("tab") === "flashcards" ? "flashcards" : "quiz";

  return (
    <PageShell width="narrow">
      <BackLink
        sector="exam"
        label={t("exam.practice.back")}
        onClick={() => navigate(-1)}
      />

      {status === "loading" && (
        <p className="py-20 text-center text-sm text-muted-foreground">
          {t("exam.practice.loading")}
        </p>
      )}

      {status === "error" && (
        <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-4 text-sm text-destructive">
          {error}
        </div>
      )}

      {status === "loaded" && data && (
        <>
          <div className="mb-1 flex items-center gap-2 font-display text-xs font-bold uppercase tracking-[0.12em] text-primary">
            <GraduationCap className="size-4" />
            {t("exam.practice.scopePractice", {
              scope: t(`exam.practice.scope.${data.scope}`),
            })}
          </div>
          <h1 className="text-3xl font-bold tracking-tight">
            {data.title || t("exam.practice.customTitle")}
          </h1>
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
    </PageShell>
  );
}
