import { AnimatePresence, motion } from "framer-motion";
import { useEffect } from "react";

import { beginPlaying, useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { GameCanvas } from "./GameCanvas";

/**
 * The game layer that sits over the frozen app. Phase machine:
 *   starting → "WAVE X" slam-in, then auto-advance to playing
 *   playing  → the live NOTINVASION game (canvas engine: cursor-as-player,
 *              clock/hourglass enemies, radiating spikes, upgrades)
 *   over     → GAME OVER, with the resume/new-game choice back in the hub
 *
 * The slam-in and game-over screens are permanent; the `playing` body is the
 * real canvas engine (`GameCanvas`).
 */
export function GameLayer() {
  const phase = useArcadeStore((s) => s.phase);
  const run = useArcadeStore((s) => s.run);

  if (phase === "off" || run === null) return null;

  return (
    // pointer-events-none so the live app stays clickable during play (the game's
    // input plate + the full-screen slam/over screens opt back in themselves).
    <div className="pointer-events-none fixed inset-0 z-[80]">
      <style>{arcadeStyles}</style>
      <AnimatePresence mode="wait">
        {phase === "starting" && <WaveSlam key="slam" wave={run.start_wave} />}
        {phase === "playing" && <GameCanvas key="play" />}
        {phase === "over" && <GameOver key="over" />}
      </AnimatePresence>
    </div>
  );
}

function WaveSlam({ wave }: { wave: number }) {
  useEffect(() => {
    const id = setTimeout(beginPlaying, 1200);
    return () => clearTimeout(id);
  }, []);
  return (
    <motion.div
      className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-black/80"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className={`arcade-slam text-center ${ARCADE_PIXEL}`}>
        <p className="arcade-neon-cyan text-sm tracking-[0.4em]">WAVE</p>
        <p className="arcade-neon-pink mt-3 text-7xl">{wave}</p>
      </div>
    </motion.div>
  );
}

function GameOver() {
  const state = useArcadeStore((s) => s.state);
  const dismiss = useArcadeStore((s) => s.dismissGameOver);
  const openOverlay = useArcadeStore((s) => s.openOverlay);
  const lastScore = state?.high_score ?? 0;

  return (
    <motion.div
      className="pointer-events-auto absolute inset-0 flex items-center justify-center bg-black/85"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className={`flex flex-col items-center gap-5 text-center ${ARCADE_PIXEL}`}>
        <p className="arcade-neon-pink text-2xl">GAME OVER</p>
        <div className="text-[9px]">
          <span className="arcade-dim">HI-SCORE </span>
          <span className="arcade-neon-yellow">{lastScore}</span>
        </div>
        {state && state.resumable_wave > 0 && (
          <p className="arcade-dim text-[7px] leading-relaxed">
            RESUME WAVE {state.resumable_wave}
            <br />
            FROM THE ARCADE ({state.resume_cost} COINS)
          </p>
        )}
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => {
              dismiss();
              openOverlay();
            }}
            className="rounded border border-cyan-400/60 arcade-neon-cyan px-4 py-2 text-[8px] transition hover:scale-105"
          >
            ARCADE
          </button>
          <button
            type="button"
            onClick={dismiss}
            className="rounded border border-white/30 arcade-dim px-4 py-2 text-[8px] transition hover:scale-105"
          >
            EXIT
          </button>
        </div>
      </div>
    </motion.div>
  );
}
