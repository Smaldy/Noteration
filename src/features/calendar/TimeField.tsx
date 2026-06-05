import { AnimatePresence, motion } from "framer-motion";
import { Clock } from "lucide-react";
import { useTranslation } from "react-i18next";

import { TimeWheel } from "@/components/TimeWheel";
import { Switch } from "@/components/ui/switch";

interface Props {
  /** Whether a specific time is set (off = all-day). */
  enabled: boolean;
  onToggle: (on: boolean) => void;
  /** "HH:MM" (24h). */
  time: string;
  onTime: (value: string) => void;
  disabled?: boolean;
}

/** Strip a leading zero from the hour: "09:30" → "9:30". */
function pretty(t: string): string {
  const [h, m] = t.split(":");
  return `${Number(h)}:${m}`;
}

/**
 * A toggle that reveals an iOS-style scrolling wheel. Off = all-day; on = pin to
 * a specific time. The header doubles as a live readout of the chosen time.
 */
export function TimeField({ enabled, onToggle, time, onTime, disabled }: Props) {
  const { t } = useTranslation();
  return (
    <div className="rounded-xl border bg-muted/30">
      <div className="flex items-center justify-between gap-3 px-3.5 py-3">
        <button
          type="button"
          onClick={() => !disabled && onToggle(!enabled)}
          disabled={disabled}
          className="flex flex-1 items-center gap-2.5 text-left"
        >
          <span className="grid size-8 shrink-0 place-items-center rounded-lg bg-primary-soft text-primary-soft-foreground">
            <Clock className="size-4" />
          </span>
          <span>
            <span className="block text-sm font-medium leading-none">
              {enabled
                ? t("calendar.dialog.atSpecificTime")
                : t("calendar.dialog.allDay")}
            </span>
            <span className="mt-1 block text-xs text-muted-foreground">
              {enabled
                ? t("calendar.dialog.scheduledFor", { time: pretty(time) })
                : t("calendar.dialog.noSetTime")}
            </span>
          </span>
        </button>
        <div className="flex items-center gap-3">
          <AnimatePresence initial={false}>
            {enabled && (
              <motion.span
                key="readout"
                initial={{ opacity: 0, x: 6 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 6 }}
                className="font-display text-lg font-semibold tabular-nums text-primary"
              >
                {pretty(time)}
              </motion.span>
            )}
          </AnimatePresence>
          <Switch
            checked={enabled}
            onCheckedChange={(v) => onToggle(v)}
            disabled={disabled}
          />
        </div>
      </div>

      <AnimatePresence initial={false}>
        {enabled && (
          <motion.div
            key="wheel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
            className="overflow-hidden"
          >
            <div className="flex justify-center px-3 pb-4 pt-1">
              <TimeWheel value={time} onChange={onTime} />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
