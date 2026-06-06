import { BookmarkPlus, Check, ExternalLink } from "lucide-react";
import { useState } from "react";

import { MarkdownView } from "@/components/MarkdownView";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import type { DuplicateResult } from "@/types/duplicator";

import { VizRouter } from "./renderers/VizRouter";

interface Props {
  result: DuplicateResult;
  topic: string;
  subtopic: string | null;
  yearLevel: number;
}

export function DuplicateResultCard({ result, topic, subtopic, yearLevel }: Props) {
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);

  const save = async () => {
    setSaving(true);
    try {
      await api.post("/duplicator/calibration/samples", {
        topic,
        subtopic,
        year_level: yearLevel,
        source_text: result.problem_text,
      });
      setSaved(true);
    } catch {
      // Non-fatal — the button just doesn't flip to "saved".
    } finally {
      setSaving(false);
    }
  };

  const score = result.difficulty_score;

  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <div className="text-sm">
        <MarkdownView>{result.problem_text}</MarkdownView>
      </div>

      <VizRouter viz={result.viz} />

      {score !== null && (
        <div className="mt-3 flex items-center gap-2">
          <span className="text-xs text-muted-foreground">Difficulty</span>
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
            Source
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
              <Check className="h-3 w-3" /> Saved
            </>
          ) : (
            <>
              <BookmarkPlus className="h-3 w-3" /> Save to calibration
            </>
          )}
        </Button>
      </div>
    </div>
  );
}
