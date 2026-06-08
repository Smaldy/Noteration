import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { beginPlaying, useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";

/**
 * The game layer that sits over the frozen app. Phase machine:
 *   starting → "WAVE X" slam-in, then auto-advance to playing
 *   playing  → the live game (Wave 2: a survival placeholder; the canvas engine,
 *              enemies, projectiles, and bombs land in the next waves)
 *   over     → GAME OVER, with the resume/new-game choice back in the hub
 *
 * The slam-in and game-over screens are permanent; only the `playing` body is a
 * placeholder, so the real engine drops straight in here later.
 */
export function GameLayer() {
  const phase = useArcadeStore((s) => s.phase);
  const run = useArcadeStore((s) => s.run);

  if (phase === "off" || run === null) return null;

  return (
    <div className="fixed inset-0 z-[80]">
      <style>{arcadeStyles}</style>
      <AnimatePresence mode="wait">
        {phase === "starting" && <WaveSlam key="slam" wave={run.start_wave} />}
        {phase === "playing" && <PlayingPlaceholder key="play" />}
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
      className="absolute inset-0 flex items-center justify-center bg-black/80"
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

/** Wave-2 placeholder: a survival timer so the economy loop (earn score → buy
 *  upgrades; die → resume) is fully exercisable before the engine exists. */
function PlayingPlaceholder() {
  const run = useArcadeStore((s) => s.run);
  const endRun = useArcadeStore((s) => s.endRun);
  const [score, setScore] = useState(run?.start_score ?? 0);
  const startWave = run?.start_wave ?? 1;
  const ended = useRef(false);

  useEffect(() => {
    const id = setInterval(() => setScore((s) => s + 10 * startWave), 1000);
    return () => clearInterval(id);
  }, [startWave]);

  function end(died: boolean) {
    if (ended.current) return;
    ended.current = true;
    void endRun(startWave, score, died);
  }

  return (
    <motion.div
      className="absolute inset-0 flex flex-col items-center justify-center bg-black/85"
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
    >
      <div className={`flex flex-col items-center gap-6 text-center ${ARCADE_PIXEL}`}>
        <div className="flex gap-8 text-[10px]">
          <span className="arcade-neon-cyan">WAVE {startWave}</span>
          <span className="arcade-neon-yellow">SCORE {score}</span>
        </div>
        <div className="max-w-xs rounded-lg border border-fuchsia-400/30 bg-black/50 p-5">
          <p className="arcade-neon-green text-[9px] leading-relaxed">
            GAME ENGINE
            <br />
            UNDER CONSTRUCTION
          </p>
          <p className="arcade-dim mt-3 text-[7px] leading-relaxed">
            ENEMIES, PROJECTILES + BOMBS
            <br />
            ARRIVE IN THE NEXT WAVE.
            <br />
            SURVIVING BANKS SCORE.
          </p>
        </div>
        <div className="flex gap-3">
          <button
            type="button"
            onClick={() => end(true)}
            className="rounded border border-rose-400/60 arcade-neon-pink px-4 py-2 text-[8px] transition hover:scale-105"
          >
            END RUN
          </button>
        </div>
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
      className="absolute inset-0 flex items-center justify-center bg-black/85"
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
