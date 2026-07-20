import { Sparkles } from "lucide-react";
import { useTranslation } from "react-i18next";

import { useAssistantStore } from "@/stores/assistant";

/** The floating pill that opens the AI sidebar — lives with the to-do and
 *  Pomodoro widgets. Hidden while the panel is open (it has its own close). */
export function AssistantLauncher() {
  const { t } = useTranslation();
  const open = useAssistantStore((s) => s.open);
  const setOpen = useAssistantStore((s) => s.setOpen);

  if (open) return null;
  return (
    <button
      type="button"
      onClick={() => setOpen(true)}
      title={t("assistant.open")}
      aria-label={t("assistant.open")}
      className="glass flex size-11 items-center justify-center rounded-full border shadow-lg transition-shadow hover:shadow-xl"
    >
      <Sparkles className="size-5 text-primary" />
    </button>
  );
}
