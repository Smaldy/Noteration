import { AnimatePresence, motion } from "framer-motion";
import {
  Brain,
  ChevronDown,
  Coffee,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
} from "lucide-react";
import { useEffect } from "react";
import { useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";
import { usePomodoroStore } from "@/stores/pomodoro";
import { useSettingsStore } from "@/stores/settings";

function fmt(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function PomodoroWidget() {
  const settings = useSettingsStore((s) => s.settings);
  const {
    phase,
    running,
    remaining,
    workSessions,
    expanded,
    workMin,
    breakMin,
    configure,
    toggle,
    reset,
    skip,
    tick,
    setExpanded,
  } = usePomodoroStore();

  // Keep durations in sync with Settings (work/break minutes).
  useEffect(() => {
    if (settings) configure(settings.pomodoro_work_min, settings.pomodoro_break_min);
  }, [settings, configure]);

  // Drive the countdown while running; also resync when the tab regains focus.
  useEffect(() => {
    if (!running) return;
    const id = setInterval(tick, 250);
    const onVisible = () => tick();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [running, tick]);

  const isWork = phase === "work";
  const total = (isWork ? workMin : breakMin) * 60;
  const fraction = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0;
  const accent = isWork ? "var(--primary)" : "#10b981"; // focus vs break

  // Lift above the Settings page's sticky bottom save bar.
  const onSettings = useLocation().pathname === "/settings";

  return (
    <div
      className={cn(
        "fixed right-4 z-40 print:hidden",
        onSettings ? "bottom-24" : "bottom-4",
      )}
    >
      <AnimatePresence mode="wait" initial={false}>
        {expanded ? (
          <motion.div
            key="panel"
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="glass w-64 rounded-2xl border p-5 shadow-xl"
          >
            <div className="mb-4 flex items-center justify-between">
              <span
                className="inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.12em]"
                style={{ color: accent }}
              >
                {isWork ? <Brain className="size-4" /> : <Coffee className="size-4" />}
                {isWork ? "Focus" : "Break"}
              </span>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                title="Minimize"
              >
                <ChevronDown className="size-4" />
              </button>
            </div>

            <Ring fraction={fraction} accent={accent}>
              <span className="font-display text-3xl font-bold tabular-nums tracking-tight">
                {fmt(remaining)}
              </span>
            </Ring>

            <div className="mt-5 flex items-center justify-center gap-3">
              <IconBtn label="Reset" onClick={reset}>
                <RotateCcw className="size-4" />
              </IconBtn>
              <button
                type="button"
                onClick={toggle}
                className="flex size-12 items-center justify-center rounded-full text-white shadow-md transition-transform active:scale-95"
                style={{ backgroundColor: accent }}
                title={running ? "Pause" : "Start"}
              >
                {running ? (
                  <Pause className="size-5 fill-current" />
                ) : (
                  <Play className="size-5 translate-x-0.5 fill-current" />
                )}
              </button>
              <IconBtn label="Skip to next phase" onClick={skip}>
                <SkipForward className="size-4" />
              </IconBtn>
            </div>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              {workSessions} focus {workSessions === 1 ? "session" : "sessions"} done
            </p>
          </motion.div>
        ) : (
          <motion.button
            key="pill"
            type="button"
            onClick={() => setExpanded(true)}
            initial={{ opacity: 0, y: 12, scale: 0.96 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 12, scale: 0.96 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
            className="glass flex items-center gap-2.5 rounded-full border py-2 pl-3 pr-2 shadow-lg transition-shadow hover:shadow-xl"
            title="Open Pomodoro timer"
          >
            <span
              className={cn("size-2 rounded-full", running && "animate-pulse")}
              style={{ backgroundColor: accent }}
            />
            <span className="font-display text-sm font-bold tabular-nums">
              {fmt(remaining)}
            </span>
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                toggle();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  toggle();
                }
              }}
              className="flex size-7 items-center justify-center rounded-full text-white"
              style={{ backgroundColor: accent }}
              title={running ? "Pause" : "Start"}
            >
              {running ? (
                <Pause className="size-3.5 fill-current" />
              ) : (
                <Play className="size-3.5 translate-x-px fill-current" />
              )}
            </span>
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}

function Ring({
  fraction,
  accent,
  children,
}: {
  fraction: number;
  accent: string;
  children: React.ReactNode;
}) {
  const r = 52;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative mx-auto size-36">
      <svg className="size-full -rotate-90" viewBox="0 0 120 120">
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          strokeWidth="8"
          className="stroke-muted"
        />
        <circle
          cx="60"
          cy="60"
          r={r}
          fill="none"
          strokeWidth="8"
          strokeLinecap="round"
          stroke={accent}
          strokeDasharray={c}
          strokeDashoffset={c * (1 - fraction)}
          style={{ transition: "stroke-dashoffset 0.3s linear" }}
        />
      </svg>
      <div className="absolute inset-0 flex items-center justify-center">
        {children}
      </div>
    </div>
  );
}

function IconBtn({
  children,
  label,
  onClick,
}: {
  children: React.ReactNode;
  label: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={label}
      aria-label={label}
      className="flex size-9 items-center justify-center rounded-full border text-muted-foreground transition-colors hover:bg-accent hover:text-foreground active:scale-95"
    >
      {children}
    </button>
  );
}
