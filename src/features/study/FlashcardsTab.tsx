import { motion } from "framer-motion";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { MarkdownView } from "@/components/MarkdownView";
import { Button } from "@/components/ui/button";
import { emitStudyEvent } from "@/lib/arcadeEvents";
import { cn } from "@/lib/utils";
import { ApiError, api } from "@/lib/api";
import type { FlashcardContent } from "@/types/study";

import { GenerateMore } from "./GenerateMore";
import { GoDeeper } from "./GoDeeper";

type Grade = "correct" | "incorrect" | "skip";

interface FlashcardsTabProps {
  /** Present for a single topic (enables "Generate more"); omitted for pooled decks. */
  topicId?: number;
  flashcards: FlashcardContent[];
  /** Full-screen study mode: gradient stage behind a larger, zoomed card. */
  fullscreen?: boolean;
}

export function FlashcardsTab({
  topicId,
  flashcards,
  fullscreen = false,
}: FlashcardsTabProps) {
  const { t } = useTranslation();
  const [index, setIndex] = useState(0);
  const [flipped, setFlipped] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset when the deck changes (e.g. switching topics).
  useEffect(() => {
    setIndex(0);
    setFlipped(false);
    setError(null);
  }, [flashcards]);

  if (flashcards.length === 0) {
    return (
      <div className="py-12 text-center">
        <p className="text-sm text-muted-foreground">
          {topicId != null
            ? t("study.flashcards.emptyTopic")
            : t("study.flashcards.emptyPooled")}
        </p>
        {topicId != null && (
          <div className="mt-4 flex justify-center">
            <GenerateMore topicId={topicId} kind="flashcards" />
          </div>
        )}
      </div>
    );
  }

  if (index >= flashcards.length) {
    return (
      <div className="py-12 text-center">
        <p className="text-lg font-medium">{t("study.flashcards.deckComplete")}</p>
        <div className="mt-6 flex items-center justify-center gap-2">
          <Button
            variant="outline"
            onClick={() => {
              setIndex(0);
              setFlipped(false);
            }}
          >
            {t("study.flashcards.reviewAgain")}
          </Button>
          {topicId != null && <GenerateMore topicId={topicId} kind="flashcards" />}
        </div>
      </div>
    );
  }

  const card = flashcards[index];

  async function grade(g: Grade) {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/study/flashcards/${card.id}/review`, { grade: g });
      emitStudyEvent("flashcard"); // additive: feeds the arcade coin economy
      setIndex((i) => i + 1);
      setFlipped(false);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : t("study.flashcards.gradeError"),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col items-center">
      <p className="mb-3 text-xs text-muted-foreground">
        {t("study.flashcards.cardProgress", {
          current: index + 1,
          total: flashcards.length,
        })}
      </p>

      <motion.div
        key={fullscreen ? "fs" : "inline"}
        initial={fullscreen ? { opacity: 0, scale: 0.96, y: 12 } : false}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.32, ease: [0.22, 1, 0.36, 1] }}
        role="button"
        tabIndex={0}
        aria-label={t("study.flashcards.clickToReveal")}
        className={cn(
          "w-full cursor-pointer rounded-2xl [perspective:1600px] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
          fullscreen ? "max-w-2xl" : "max-w-xl",
        )}
        onClick={() => setFlipped((f) => !f)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            setFlipped((f) => !f);
          }
        }}
      >
        <motion.div
          className={cn(
            "relative w-full [transform-style:preserve-3d]",
            fullscreen ? "min-h-72" : "min-h-48",
          )}
          animate={{ rotateY: flipped ? 180 : 0 }}
          transition={{ duration: 0.5, ease: [0.22, 1, 0.36, 1] }}
        >
          <CardFace
            label={t("study.flashcards.front")}
            text={card.front}
            big={fullscreen}
          />
          <CardFace
            label={t("study.flashcards.back")}
            text={card.back}
            flipped
            big={fullscreen}
          />
        </motion.div>
      </motion.div>

      {!flipped ? (
        <p className="mt-4 text-sm text-muted-foreground">
          {t("study.flashcards.clickToReveal")}
        </p>
      ) : (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.25 }}
          className="mt-5 flex gap-2"
        >
          <Button
            variant="outline"
            onClick={() => void grade("incorrect")}
            disabled={busy}
          >
            {t("study.flashcards.incorrect")}
          </Button>
          <Button
            variant="ghost"
            onClick={() => void grade("skip")}
            disabled={busy}
          >
            {t("study.flashcards.skip")}
          </Button>
          <Button onClick={() => void grade("correct")} disabled={busy}>
            {t("study.flashcards.correct")}
          </Button>
        </motion.div>
      )}

      {flipped && (
        <div className="mt-3">
          <GoDeeper text={`${card.front}\n${card.back}`} />
        </div>
      )}

      {error && <p className="mt-3 text-sm text-destructive">{error}</p>}

      {topicId != null && (
        <div className="mt-6">
          <GenerateMore topicId={topicId} kind="flashcards" />
        </div>
      )}
    </div>
  );
}

function CardFace({
  label,
  text,
  flipped = false,
  big = false,
}: {
  label: string;
  text: string;
  flipped?: boolean;
  big?: boolean;
}) {
  return (
    <div
      className={cn(
        "absolute inset-0 flex items-center justify-center rounded-2xl border bg-card text-center [backface-visibility:hidden]",
        big ? "focus-float p-10 text-2xl" : "p-8 text-lg shadow-sm",
        flipped && "[transform:rotateY(180deg)]",
      )}
    >
      <div>
        <p className="mb-1 text-xs uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p>
          <MarkdownView inline>{text}</MarkdownView>
        </p>
      </div>
    </div>
  );
}
