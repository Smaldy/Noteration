import { Sparkles } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";
import { useStudyStore } from "@/stores/study";

/**
 * "Generate more" button for a topic's quiz or flashcards. Shared by QuizTab and
 * FlashcardsTab, which differ only in the content kind and their i18n namespace.
 */
export function GenerateMore({
  topicId,
  kind,
  align = "center",
}: {
  topicId: number;
  kind: "mcqs" | "flashcards";
  /** Button column alignment (quiz aligns left, flashcards centers). */
  align?: "start" | "center";
}) {
  const { t } = useTranslation();
  const generateMore = useStudyStore((s) => s.generateMore);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const ns = kind === "mcqs" ? "study.quiz" : "study.flashcards";

  async function run() {
    setBusy(true);
    setError(null);
    try {
      await generateMore(topicId, kind);
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : t(`${ns}.generateMoreError`),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      className={cn(
        "flex flex-col gap-1",
        align === "start" ? "items-start" : "items-center",
      )}
    >
      <Button variant="ghost" size="sm" onClick={() => void run()} disabled={busy}>
        <Sparkles />
        {busy ? t(`${ns}.generating`) : t(`${ns}.generateMore`)}
      </Button>
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
