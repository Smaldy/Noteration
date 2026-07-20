import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { emitAiContext } from "@/lib/aiContext";
import { cn } from "@/lib/utils";

/**
 * The card "go deeper" emitter: a deliberately two-step affordance on quiz
 * questions and flashcards. The first tap only expands a confirm row, keeping
 * the AI ask out of the rapid answer/grade muscle-memory path; confirming
 * emits one aiContext event with the card text and a static instruction.
 */
export function GoDeeper({ text, className }: { text: string; className?: string }) {
  const { t } = useTranslation();
  const [expanded, setExpanded] = useState(false);

  // Moving to the next card collapses a left-open confirm row.
  useEffect(() => setExpanded(false), [text]);

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={() => setExpanded(true)}
        className={cn(
          "inline-flex items-center gap-1 rounded-md px-1.5 py-1 text-[11px] font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground",
          className,
        )}
      >
        <Sparkles className="size-3.5" />
        {t("assistant.goDeeper.label")}
      </button>
    );
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 4 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.18 }}
      className={cn("flex flex-wrap items-center justify-end gap-2", className)}
    >
      <span className="text-xs text-muted-foreground">
        {t("assistant.goDeeper.hint")}
      </span>
      <button
        type="button"
        onClick={() => {
          emitAiContext({ text, instruction: t("assistant.goDeeper.prompt") });
          setExpanded(false);
        }}
        className="inline-flex items-center gap-1 rounded-md bg-primary px-2 py-1 text-[11px] font-medium text-primary-foreground transition-opacity hover:opacity-90"
      >
        <Sparkles className="size-3.5" />
        {t("assistant.goDeeper.ask")}
      </button>
    </motion.div>
  );
}
