import { motion } from "framer-motion";
import { Check, X } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { MCQ } from "@/types/study";

import { GenerateMore } from "./GenerateMore";

interface QuizTabProps {
  /** Present for a single topic (enables "Generate more"); omitted for pooled decks. */
  topicId?: number;
  mcqs: MCQ[];
  /** Full-screen study mode: gradient stage, zoomed text, slide-in per question. */
  fullscreen?: boolean;
}

export function QuizTab({ topicId, mcqs, fullscreen = false }: QuizTabProps) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [revealed, setRevealed] = useState(false);
  const [correct, setCorrect] = useState(0);
  const [finished, setFinished] = useState(false);

  if (mcqs.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-muted-foreground">
          {topicId != null
            ? t("study.quiz.emptyTopic")
            : t("study.quiz.emptyPooled")}
        </p>
        {topicId != null && (
          <div className="mt-4 flex justify-center">
            <GenerateMore topicId={topicId} kind="mcqs" align="start" />
          </div>
        )}
      </div>
    );
  }

  function restart() {
    setIndex(0);
    setSelected(null);
    setRevealed(false);
    setCorrect(0);
    setFinished(false);
  }

  if (finished) {
    return (
      <div className="py-12 text-center">
        <p className="text-2xl font-semibold">
          {correct} / {mcqs.length}
        </p>
        <p className="mt-1 text-sm text-muted-foreground">
          {correct === mcqs.length
            ? t("study.quiz.perfect")
            : t("study.quiz.reviewMissed")}
        </p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Button variant="outline" onClick={restart}>
            {t("study.quiz.tryAgain")}
          </Button>
          {topicId != null && <GenerateMore topicId={topicId} kind="mcqs" align="start" />}
        </div>
      </div>
    );
  }

  const mcq = mcqs[index];

  function choose(i: number) {
    if (revealed) return;
    setSelected(i);
    setRevealed(true);
    if (i === mcq.correct_index) setCorrect((c) => c + 1);
  }

  function next() {
    if (index === mcqs.length - 1) {
      setFinished(true);
      return;
    }
    setIndex((i) => i + 1);
    setSelected(null);
    setRevealed(false);
  }

  return (
    <div
      className={cn(
        fullscreen && "focus-card focus-float rounded-2xl p-6 sm:p-8",
      )}
    >
      <div className="mb-4 h-1.5 w-full overflow-hidden rounded-full bg-muted">
        <div
          className="h-full bg-primary transition-all"
          style={{ width: `${(index / mcqs.length) * 100}%` }}
        />
      </div>
      <p className="mb-1 text-xs text-muted-foreground">
        {t("study.quiz.questionProgress", {
          current: index + 1,
          total: mcqs.length,
        })}
      </p>

      <motion.div
        key={index}
        initial={fullscreen ? { opacity: 0, x: 28 } : false}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
      >
        <h3 className={cn("font-medium", fullscreen ? "text-2xl" : "text-lg")}>
          {mcq.question}
        </h3>

        <div className="mt-4 space-y-2">
          {mcq.options.map((option, i) => {
            const isCorrect = i === mcq.correct_index;
            const isChosen = i === selected;
            return (
              <button
                key={i}
                type="button"
                onClick={() => choose(i)}
                disabled={revealed}
                className={cn(
                  "flex w-full items-center justify-between rounded-md border px-3 py-2 text-left transition-colors",
                  fullscreen ? "text-base" : "text-sm",
                  !revealed && "hover:bg-accent/50",
                  revealed && isCorrect && "border-emerald-500/60 bg-emerald-500/10",
                  revealed &&
                    isChosen &&
                    !isCorrect &&
                    "border-destructive/60 bg-destructive/10",
                )}
              >
                <span>{option}</span>
                {revealed && isCorrect && (
                  <Check className="size-4 text-emerald-600" />
                )}
                {revealed && isChosen && !isCorrect && (
                  <X className="size-4 text-destructive" />
                )}
              </button>
            );
          })}
        </div>
      </motion.div>

      {revealed && (
        <div className="mt-4 rounded-md bg-muted/50 p-3 text-sm">
          {mcq.explanation ? (
            <p>{mcq.explanation}</p>
          ) : (
            <p className="text-muted-foreground">{t("study.quiz.noExplanation")}</p>
          )}
        </div>
      )}

      <div className="mt-6 flex items-center justify-between gap-2">
        {topicId != null ? <GenerateMore topicId={topicId} kind="mcqs" align="start" /> : <span />}
        <Button onClick={next} disabled={!revealed}>
          {index === mcqs.length - 1 ? t("study.quiz.finish") : t("study.quiz.next")}
        </Button>
      </div>
    </div>
  );
}

