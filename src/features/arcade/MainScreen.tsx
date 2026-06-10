import { ChevronRight } from "lucide-react";

import type { ArcadeState } from "@/types/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { useCountdown } from "./useCountdown";

export type StartMode = "fresh" | "resume";

/** The CRT's main attract screen: records + the New Start / Continue selector.
 *  The lever (on the deck) starts whichever option is selected. During a
 *  cooldown the selector is replaced by the countdown. */
export function MainScreen({
  state,
  selection,
}: {
  state: ArcadeState;
  selection: StartMode;
}) {
  const cooldown = useCountdown(state.cooldown_until);
  const canResume = state.resumable_wave > 0 && state.resume_cost != null;
  const continuesLeft = Math.max(0, state.max_continues - state.resume_count);
  // A saved run exists but its continues are spent → the lineage is forced to end.
  const exhausted = state.resumable_wave > 0 && state.resume_cost == null;

  return (
    <div className={`flex h-full flex-col items-center justify-between text-center ${ARCADE_PIXEL}`}>
      <div>
        <p className="arcade-neon-pink text-[12px] tracking-[0.35em]">NOTINVASION</p>
        <div className="mt-2 flex justify-center gap-6 text-[8px]">
          <span className="arcade-dim">HI <span className="arcade-neon-yellow">{state.high_score}</span></span>
          <span className="arcade-dim">WAVE <span className="arcade-neon-green">{state.wave_record}</span></span>
        </div>
      </div>

      {cooldown.active ? (
        <div className="flex flex-col items-center gap-2">
          <p className="arcade-neon-pink text-[10px]">COOLING DOWN</p>
          <p className="arcade-neon-cyan text-3xl tabular-nums">{cooldown.label}</p>
          <p className="arcade-dim text-[7px]">GO STUDY — COME BACK SOON</p>
        </div>
      ) : (
        <div className="flex w-full flex-col gap-2.5">
          <Option
            active={selection === "fresh"}
            affordable={state.coins >= state.economy.base_cost}
            label={`INSERT ${state.economy.base_cost} COINS TO START`}
          />
          <Option
            active={selection === "resume"}
            affordable={canResume && state.coins >= (state.resume_cost ?? 0)}
            disabled={!canResume}
            label={
              canResume
                ? `CONTINUE W${state.resumable_wave} · ${state.resume_cost}`
                : exhausted
                  ? "NO CONTINUES LEFT"
                  : "CONTINUE —"
            }
          />
          {canResume ? (
            <p className="arcade-dim text-[6px] tracking-[0.2em]">
              {continuesLeft} OF {state.max_continues} CONTINUES LEFT
            </p>
          ) : exhausted ? (
            <p className="arcade-neon-pink text-[6px] tracking-[0.2em]">
              RUN ENDED — START A NEW GAME
            </p>
          ) : null}
        </div>
      )}

      <p className="arcade-dim text-[7px]">
        {cooldown.active ? "TIMER RUNNING" : "▲▼ SELECT · PULL LEVER ►"}
      </p>
    </div>
  );
}

function Option({
  active,
  affordable,
  disabled,
  label,
}: {
  active: boolean;
  affordable: boolean;
  disabled?: boolean;
  label: string;
}) {
  return (
    <div
      className={`relative flex items-center justify-center gap-2 rounded-md border px-3 py-2.5 text-[9px] transition ${
        disabled
          ? "border-white/10 arcade-dim opacity-50"
          : active
            ? "border-fuchsia-300/70 bg-fuchsia-500/10"
            : "border-white/15"
      }`}
    >
      {active && !disabled && (
        <ChevronRight className="absolute left-2 size-3 arcade-neon-pink arcade-blink" />
      )}
      <span
        className={
          disabled
            ? ""
            : active
              ? affordable
                ? "arcade-neon-cyan arcade-blink"
                : "arcade-neon-pink"
              : "arcade-dim"
        }
      >
        {label}
      </span>
    </div>
  );
}
