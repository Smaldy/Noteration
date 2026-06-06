import { AnimatePresence, motion } from "framer-motion";
import {
  Brain,
  ChevronDown,
  Coffee,
  Music,
  Pause,
  Play,
  RotateCcw,
  SkipForward,
  Upload,
  Volume2,
  VolumeX,
  X,
} from "lucide-react";
import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useLocation } from "react-router-dom";
import { useShallow } from "zustand/react/shallow";

import { cn } from "@/lib/utils";
import * as audio from "@/features/pomodoro/audio";
import type { SoundKind } from "@/features/pomodoro/audio";
import { usePomodoroStore } from "@/stores/pomodoro";
import { useSettingsStore } from "@/stores/settings";
import { useSoundStore } from "@/stores/sound";

function fmt(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

export function PomodoroWidget() {
  const { t } = useTranslation();
  const settings = useSettingsStore((s) => s.settings);
  // `remaining` ticks 4×/sec; it's subscribed to separately inside <TimerFace>
  // and <PillTime> so the panel chrome and sound controls don't re-render on it.
  const {
    phase,
    running,
    workSessions,
    expanded,
    completedTick,
    configure,
    toggle,
    reset,
    skip,
    tick,
    setExpanded,
  } = usePomodoroStore(
    useShallow((s) => ({
      phase: s.phase,
      running: s.running,
      workSessions: s.workSessions,
      expanded: s.expanded,
      completedTick: s.completedTick,
      configure: s.configure,
      toggle: s.toggle,
      reset: s.reset,
      skip: s.skip,
      tick: s.tick,
      setExpanded: s.setExpanded,
    })),
  );

  const sound = useSoundStore();
  const fileInput = useRef<HTMLInputElement>(null);
  const prevCompleted = useRef(completedTick);

  // Keep durations in sync with Settings (work/break minutes).
  useEffect(() => {
    if (settings) configure(settings.pomodoro_work_min, settings.pomodoro_break_min);
  }, [settings, configure]);

  // Load persisted sound prefs + custom file once.
  useEffect(() => {
    void sound.hydrate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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

  // Ambient bed plays while the timer is running.
  useEffect(() => {
    if (running && sound.kind !== "none") audio.startAmbient(sound.kind);
    else audio.stopAmbient();
  }, [running, sound.kind, sound.customLoaded]);

  // Live volume / mute.
  useEffect(() => {
    audio.setVolume(sound.muted ? 0 : sound.volume);
  }, [sound.muted, sound.volume]);

  // Ring the alarm when a phase finishes.
  useEffect(() => {
    if (completedTick !== prevCompleted.current) {
      prevCompleted.current = completedTick;
      audio.playAlarm(sound.muted);
    }
  }, [completedTick, sound.muted]);

  function onPick(kind: SoundKind) {
    if (kind === "custom" && !sound.customLoaded) {
      fileInput.current?.click();
      return;
    }
    void audio.unlock();
    sound.setKind(kind);
  }

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (file) void sound.loadCustomFile(file);
    e.target.value = ""; // allow re-picking the same file
  }

  function handleToggle() {
    void audio.unlock();
    toggle();
  }

  const isWork = phase === "work";
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
                {isWork ? t("pomodoro.focus") : t("pomodoro.break")}
              </span>
              <button
                type="button"
                onClick={() => setExpanded(false)}
                className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                title={t("pomodoro.minimize")}
              >
                <ChevronDown className="size-4" />
              </button>
            </div>

            <TimerFace accent={accent} isWork={isWork} />

            <div className="mt-5 flex items-center justify-center gap-3">
              <IconBtn label={t("pomodoro.reset")} onClick={reset}>
                <RotateCcw className="size-4" />
              </IconBtn>
              <button
                type="button"
                onClick={handleToggle}
                className="flex size-12 items-center justify-center rounded-full text-white shadow-md transition-transform active:scale-95"
                style={{ backgroundColor: accent }}
                title={running ? t("pomodoro.pause") : t("pomodoro.start")}
              >
                {running ? (
                  <Pause className="size-5 fill-current" />
                ) : (
                  <Play className="size-5 translate-x-0.5 fill-current" />
                )}
              </button>
              <IconBtn label={t("pomodoro.skip")} onClick={skip}>
                <SkipForward className="size-4" />
              </IconBtn>
            </div>

            <p className="mt-4 text-center text-xs text-muted-foreground">
              {t("pomodoro.sessionsDone", { count: workSessions })}
            </p>

            {/* Ambient sound */}
            <div className="mt-4 border-t pt-4">
              <div className="mb-2 flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  {t("pomodoro.sound")}
                </span>
                <button
                  type="button"
                  onClick={sound.toggleMuted}
                  title={sound.muted ? t("pomodoro.unmute") : t("pomodoro.mute")}
                  aria-label={sound.muted ? t("pomodoro.unmute") : t("pomodoro.mute")}
                  className="rounded-md p-1 text-muted-foreground transition-colors hover:text-foreground"
                >
                  {sound.muted ? (
                    <VolumeX className="size-4" />
                  ) : (
                    <Volume2 className="size-4" />
                  )}
                </button>
              </div>

              <div className="flex flex-wrap gap-1.5">
                {(["none", "rain", "sea"] as SoundKind[]).map((k) => (
                  <SoundChip
                    key={k}
                    label={t(`pomodoro.${k}`)}
                    active={sound.kind === k}
                    onClick={() => onPick(k)}
                  />
                ))}
                <SoundChip
                  label={sound.customLoaded ? t("pomodoro.custom") : t("pomodoro.upload")}
                  icon={sound.customLoaded ? <Music /> : <Upload />}
                  active={sound.kind === "custom"}
                  onClick={() => onPick("custom")}
                />
              </div>

              {sound.customLoaded && sound.customName && (
                <div className="mt-2 flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Music className="size-3 shrink-0" />
                  <span className="min-w-0 flex-1 truncate" title={sound.customName}>
                    {sound.customName}
                  </span>
                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    className="shrink-0 rounded px-1 hover:text-foreground"
                    title={t("pomodoro.replace")}
                  >
                    {t("pomodoro.replace")}
                  </button>
                  <button
                    type="button"
                    onClick={() => void sound.clearCustom()}
                    className="shrink-0 rounded p-0.5 hover:text-destructive"
                    title={t("pomodoro.remove")}
                    aria-label={t("pomodoro.removeCustom")}
                  >
                    <X className="size-3.5" />
                  </button>
                </div>
              )}

              {sound.customError && (
                <p className="mt-2 text-xs text-destructive">{sound.customError}</p>
              )}

              <input
                ref={fileInput}
                type="file"
                accept="audio/*"
                onChange={onFile}
                className="hidden"
              />

              <input
                type="range"
                min={0}
                max={1}
                step={0.05}
                value={sound.muted ? 0 : sound.volume}
                disabled={sound.muted || sound.kind === "none"}
                onChange={(e) => sound.setVolume(Number(e.target.value))}
                className="mt-3 w-full accent-[var(--primary)] disabled:opacity-40"
                aria-label={t("pomodoro.volume")}
              />
            </div>
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
            title={t("pomodoro.openTimer")}
          >
            <span
              className={cn("size-2 rounded-full", running && "animate-pulse")}
              style={{ backgroundColor: accent }}
            />
            <PillTime />
            <span
              role="button"
              tabIndex={0}
              onClick={(e) => {
                e.stopPropagation();
                handleToggle();
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  e.stopPropagation();
                  handleToggle();
                }
              }}
              className="flex size-7 items-center justify-center rounded-full text-white"
              style={{ backgroundColor: accent }}
              title={running ? t("pomodoro.pause") : t("pomodoro.start")}
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

// Subscribes to the fast-ticking `remaining` in isolation so the expanded panel
// (sound controls, buttons, chips) doesn't re-render on every countdown frame.
function TimerFace({ accent, isWork }: { accent: string; isWork: boolean }) {
  const remaining = usePomodoroStore((s) => s.remaining);
  const workMin = usePomodoroStore((s) => s.workMin);
  const breakMin = usePomodoroStore((s) => s.breakMin);
  const total = (isWork ? workMin : breakMin) * 60;
  const fraction = total > 0 ? Math.max(0, Math.min(1, remaining / total)) : 0;
  return (
    <Ring fraction={fraction} accent={accent}>
      <span className="font-display text-3xl font-bold tabular-nums tracking-tight">
        {fmt(remaining)}
      </span>
    </Ring>
  );
}

// The collapsed pill's live clock — isolated for the same reason as TimerFace.
function PillTime() {
  const remaining = usePomodoroStore((s) => s.remaining);
  return (
    <span className="font-display text-sm font-bold tabular-nums">
      {fmt(remaining)}
    </span>
  );
}

function SoundChip({
  label,
  active,
  onClick,
  icon,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
  icon?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        "inline-flex items-center gap-1 rounded-lg border px-2.5 py-1 text-xs font-medium transition-all active:scale-95 [&_svg]:size-3",
        active
          ? "border-primary bg-primary-soft text-primary-soft-foreground"
          : "text-muted-foreground hover:border-ring/40 hover:text-foreground",
      )}
    >
      {icon}
      {label}
    </button>
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
