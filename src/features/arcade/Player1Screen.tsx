import { motion } from "framer-motion";
import { Coins } from "lucide-react";
import { useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState } from "@/types/arcade";

import { ARCADE_PIXEL } from "./crtStyles";
import { useCountdown } from "./useCountdown";

/** The default arcade screen: balance, records, and the start lever (or, during
 *  a cooldown, the countdown that replaces the start prompt). */
export function Player1Screen({ state }: { state: ArcadeState }) {
  const startRun = useArcadeStore((s) => s.startRun);
  const cooldown = useCountdown(state.cooldown_until);
  const [pulling, setPulling] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canResume = state.resumable_wave > 0 && state.resume_cost != null;
  const freshCost = state.economy.base_cost;
  const resumeCost = state.resume_cost ?? 0;

  async function pull(mode: "fresh" | "resume") {
    if (pulling) return;
    setError(null);
    setPulling(true);
    // Let the lever animation play before the screen hands off to the game.
    await new Promise((r) => setTimeout(r, 480));
    const result = await startRun(mode);
    if (!result.ok) {
      setError(result.error ?? "Could not start");
      setPulling(false);
    }
  }

  return (
    <div className={`flex h-full flex-col items-center justify-between py-6 ${ARCADE_PIXEL}`}>
      <div className="text-center">
        <p className="arcade-neon-pink text-[11px] tracking-[0.3em]">PLAYER 1</p>
        <div className="mt-4 flex items-center justify-center gap-2">
          <Coins className="size-5 text-amber-300" />
          <span className="arcade-neon-yellow text-2xl">{state.coins}</span>
          <span className="arcade-dim text-[9px]">COINS</span>
        </div>
      </div>

      <div className="grid w-full grid-cols-2 gap-3 text-center text-[9px]">
        <Stat label="HI-SCORE" value={state.high_score} tone="cyan" />
        <Stat label="BEST WAVE" value={state.wave_record} tone="green" />
      </div>

      {/* Start zone: lever, or the cooldown countdown that replaces it. */}
      <div className="flex w-full flex-1 flex-col items-center justify-center">
        {cooldown.active ? (
          <Cooldown label={cooldown.label} />
        ) : (
          <div className="flex flex-col items-center gap-4">
            <Lever pulling={pulling} />
            {error && <p className="arcade-neon-pink text-[8px]">{error}</p>}
            <div className="flex flex-col items-center gap-2">
              {canResume && (
                <StartButton
                  label={`RESUME W${state.resumable_wave}`}
                  cost={resumeCost}
                  affordable={state.coins >= resumeCost}
                  disabled={pulling}
                  onClick={() => pull("resume")}
                  tone="cyan"
                />
              )}
              <StartButton
                label={canResume ? "NEW GAME" : "PULL TO START"}
                cost={freshCost}
                affordable={state.coins >= freshCost}
                disabled={pulling}
                onClick={() => pull("fresh")}
                tone="pink"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "cyan" | "green" }) {
  return (
    <div>
      <p className="arcade-dim">{label}</p>
      <p className={`mt-1 text-base arcade-neon-${tone}`}>{value}</p>
    </div>
  );
}

function Lever({ pulling }: { pulling: boolean }) {
  return (
    <div className={`relative h-20 w-12 ${pulling ? "arcade-lever-pulled" : ""}`}>
      {/* base slot */}
      <div className="absolute bottom-0 left-1/2 h-3 w-10 -translate-x-1/2 rounded-full bg-black/70 shadow-inner" />
      {/* stick + knob */}
      <div className="arcade-lever-knob absolute bottom-2 left-1/2 flex -translate-x-1/2 flex-col items-center">
        <div className="size-6 rounded-full bg-gradient-to-br from-rose-400 to-red-600 shadow-[0_0_12px_rgba(255,80,80,0.7)]" />
        <div className="h-12 w-1.5 bg-gradient-to-b from-zinc-300 to-zinc-500" />
      </div>
    </div>
  );
}

function StartButton({
  label,
  cost,
  affordable,
  disabled,
  onClick,
  tone,
}: {
  label: string;
  cost: number;
  affordable: boolean;
  disabled: boolean;
  onClick: () => void;
  tone: "pink" | "cyan";
}) {
  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled || !affordable}
      whileHover={affordable ? { scale: 1.05 } : undefined}
      whileTap={affordable ? { scale: 0.95 } : undefined}
      className={`flex flex-col items-center gap-1 rounded-md border px-4 py-2 text-[9px] transition disabled:opacity-50 ${
        affordable
          ? `border-current arcade-neon-${tone} arcade-blink`
          : "border-rose-500/40 arcade-dim"
      }`}
    >
      <span>{label}</span>
      <span className="text-[8px] text-amber-300">
        {affordable ? `${cost} COINS` : `NEED ${cost} COINS`}
      </span>
    </motion.button>
  );
}

function Cooldown({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center gap-3 text-center">
      <p className="arcade-neon-pink text-[10px]">COOLING DOWN</p>
      <p className="arcade-neon-cyan text-3xl tabular-nums">{label}</p>
      <p className="arcade-dim text-[8px]">GO STUDY — COME BACK SOON</p>
    </div>
  );
}
