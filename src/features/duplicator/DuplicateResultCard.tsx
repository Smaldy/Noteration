import { BookmarkPlus, Check, ExternalLink, Maximize2 } from "lucide-react";
import { useTranslation } from "react-i18next";

import { MarkdownView } from "@/components/MarkdownView";
import { Button } from "@/components/ui/button";
import type { DuplicateResult } from "@/types/duplicator";

import { formatProblem } from "./latex";
import { useCalibrationSave } from "./useCalibrationSave";
import { VizRouter } from "./renderers/VizRouter";

interface Props {
  result: DuplicateResult;
  topic: string;
  subtopic: string | null;
  yearLevel: number;
  onFocus: () => void;
}

export function DuplicateResultCard({
  result,
  topic,
  subtopic,
  yearLevel,
  onFocus,
}: Props) {
  const { t } = useTranslation();
  const { saved, saving, save } = useCalibrationSave(
    result,
    topic,
    subtopic,
    yearLevel,
  );
  const score = result.difficulty_score;

  return (
    <div className="group rounded-lg border border-border bg-background/60 p-3">
      <div className="mb-1 flex justify-end">
        <button
          type="button"
          onClick={onFocus}
          title={t("duplicator.actions.openVariantFullScreen")}
          aria-label={t("duplicator.actions.openVariantFullScreen")}
          className="flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-muted-foreground opacity-0 transition-colors hover:bg-accent hover:text-accent-foreground focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring group-hover:opacity-100"
        >
          <Maximize2 className="h-3.5 w-3.5" />
          {t("duplicator.actions.focus")}
        </button>
      </div>

      <div className="text-sm">
        <MarkdownView interactiveTasks>
          {formatProblem(result.problem_text)}
        </MarkdownView>
      </div>

      <VizRouter viz={result.viz} />

      {score !== null && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">{t("duplicator.result.difficulty")}</span>
          <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-muted">
            <div
              className="h-full rounded-full bg-primary"
              style={{ width: `${Math.round(Math.min(1, Math.max(0, score)) * 100)}%` }}
            />
          </div>
          <span className="w-8 text-right text-xs tabular-nums text-muted-foreground">
            {score.toFixed(2)}
          </span>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between">
        {result.source_url ? (
          <a
            href={result.source_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground hover:underline"
          >
            <ExternalLink className="h-3 w-3" />
            {t("duplicator.result.source")}
          </a>
        ) : (
          <span />
        )}
        <Button
          variant="ghost"
          size="sm"
          onClick={save}
          disabled={saving || saved}
          className="h-7 gap-1 text-xs"
        >
          {saved ? (
            <>
              <Check className="h-3 w-3" /> {t("duplicator.result.saved")}
            </>
          ) : (
            <>
              <BookmarkPlus className="h-3 w-3" /> {t("duplicator.result.saveToCalibration")}
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
