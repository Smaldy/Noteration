/** Gentle "no AI configured" nudge (spec: local AI UI placement, open question).
 *
 *  Shown where the user is about to rely on generation (upload dialog, queue
 *  page) when no provider can actually serve: no enabled Gemini key, no paid
 *  Claude, no local model. It never auto-runs anything; it deep-links to the
 *  Settings local AI section and can be dismissed for the session. Mirrors the
 *  backend's `_has_configured_provider` (services/worker.py). */

import { Sparkles, X } from "lucide-react";
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useSettingsStore } from "@/stores/settings";
import type { Settings } from "@/types/settings";

const DISMISS_KEY = "noteration.noAiNudgeDismissed";

function hasConfiguredProvider(s: Settings): boolean {
  if (s.gemini_enabled !== false && s.gemini_key_set) return true;
  if (s.allow_paid && s.claude_key_set) return true;
  if (
    s.ollama_enabled &&
    (s.ollama_model || s.ollama_fast_model || s.ollama_quality_model)
  ) {
    return true;
  }
  return false;
}

export function NoAiBanner({ className }: { className?: string }) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { settings, loadState, fetchSettings } = useSettingsStore();
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem(DISMISS_KEY) === "1",
  );

  useEffect(() => {
    if (loadState === "idle") void fetchSettings();
  }, [loadState, fetchSettings]);

  if (dismissed || !settings || hasConfiguredProvider(settings)) return null;

  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border border-primary/30 bg-primary-soft/50 p-3.5",
        className,
      )}
      role="status"
    >
      <Sparkles className="mt-0.5 size-4 shrink-0 text-primary" />
      <div className="min-w-0 flex-1 space-y-2">
        <p className="text-sm">{t("common.noAi.message")}</p>
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate("/settings#local-ai")}
        >
          {t("common.noAi.action")}
        </Button>
      </div>
      <button
        type="button"
        aria-label={t("common.noAi.dismiss")}
        className="shrink-0 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
        onClick={() => {
          sessionStorage.setItem(DISMISS_KEY, "1");
          setDismissed(true);
        }}
      >
        <X className="size-4" />
      </button>
    </div>
  );
}
