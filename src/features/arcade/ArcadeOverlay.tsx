import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, X } from "lucide-react";
import { useState } from "react";

import { useArcadeStore } from "@/stores/arcade";

import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { Player1Screen } from "./Player1Screen";
import { UpgradesScreen } from "./UpgradesScreen";

type Screen = "player1" | "upgrades";

/** The retro arcade-cabinet overlay — the hub/meta-UI. Two screens (PLAYER 1 and
 *  UPGRADES) swap via left/right arrows. Opens from the joystick button; closes
 *  to leave the real app exactly as it was. */
export function ArcadeOverlay() {
  const open = useArcadeStore((s) => s.overlayOpen);
  const close = useArcadeStore((s) => s.closeOverlay);
  const status = useArcadeStore((s) => s.status);
  const state = useArcadeStore((s) => s.state);
  const [screen, setScreen] = useState<Screen>("player1");

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="arcade-room fixed inset-0 z-[90] flex items-center justify-center p-4"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          role="dialog"
          aria-modal="true"
          aria-label="Arcade machine"
        >
          <style>{arcadeStyles}</style>

          <motion.div
            className="arcade-cabinet relative w-full max-w-sm rounded-3xl p-4 pb-6"
            initial={{ scale: 0.8, y: 30, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.85, opacity: 0 }}
            transition={{ type: "spring", stiffness: 240, damping: 22 }}
          >
            {/* Marquee */}
            <div className={`mb-3 text-center ${ARCADE_PIXEL}`}>
              <p className="arcade-neon-pink text-[10px] tracking-[0.25em]">NOTERATION</p>
              <p className="arcade-neon-cyan mt-1 text-[8px] tracking-[0.4em]">★ ARCADE ★</p>
            </div>

            <button
              type="button"
              onClick={close}
              aria-label="Close arcade"
              className="absolute right-3 top-3 z-10 grid size-7 place-items-center rounded-full bg-white/10 text-white/70 transition hover:bg-white/20 hover:text-white"
            >
              <X className="size-4" />
            </button>

            {/* Screen */}
            <div className="relative flex items-stretch gap-1">
              <NavArrow
                dir="left"
                onClick={() => setScreen(screen === "player1" ? "upgrades" : "player1")}
              />
              <div className="arcade-screen relative h-[26rem] flex-1 rounded-lg px-4">
                {state == null ? (
                  <LoadingScreen status={status} />
                ) : (
                  <AnimatePresence mode="wait">
                    <motion.div
                      key={screen}
                      className="h-full"
                      initial={{ opacity: 0, x: 24 }}
                      animate={{ opacity: 1, x: 0 }}
                      exit={{ opacity: 0, x: -24 }}
                      transition={{ duration: 0.2 }}
                    >
                      {screen === "player1" ? (
                        <Player1Screen state={state} />
                      ) : (
                        <UpgradesScreen state={state} />
                      )}
                    </motion.div>
                  </AnimatePresence>
                )}
              </div>
              <NavArrow
                dir="right"
                onClick={() => setScreen(screen === "player1" ? "upgrades" : "player1")}
              />
            </div>

            {/* Screen dots */}
            <div className="mt-3 flex justify-center gap-2">
              {(["player1", "upgrades"] as Screen[]).map((s) => (
                <span
                  key={s}
                  className={`h-2 w-2 rounded-full transition ${
                    screen === s ? "bg-fuchsia-400" : "bg-white/20"
                  }`}
                />
              ))}
            </div>

            {/* Daily quest ticker */}
            {state && <DailyQuest state={state} />}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function NavArrow({ dir, onClick }: { dir: "left" | "right"; onClick: () => void }) {
  const Icon = dir === "left" ? ChevronLeft : ChevronRight;
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={dir === "left" ? "Previous screen" : "Next screen"}
      className="grid w-7 place-items-center rounded-md bg-fuchsia-500/10 text-fuchsia-300 transition hover:bg-fuchsia-500/25"
    >
      <Icon className="size-5" />
    </button>
  );
}

function LoadingScreen({ status }: { status: string }) {
  return (
    <div className={`flex h-full items-center justify-center ${ARCADE_PIXEL}`}>
      <p className="arcade-neon-cyan arcade-blink text-[10px]">
        {status === "error" ? "NO SIGNAL" : "LOADING..."}
      </p>
    </div>
  );
}

function DailyQuest({ state }: { state: import("@/types/arcade").ArcadeState }) {
  const { mcq_count, target, completed } = state.daily_quest;
  const pct = Math.min(100, (mcq_count / target) * 100);
  return (
    <div className={`mt-4 px-1 ${ARCADE_PIXEL}`}>
      <div className="flex items-center justify-between text-[7px]">
        <span className="arcade-dim">DAILY QUEST · {target} MCQ</span>
        <span className={completed ? "arcade-neon-green" : "arcade-neon-yellow"}>
          {completed ? "+1 COIN ✓" : `${mcq_count}/${target}`}
        </span>
      </div>
      <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div
          className={`h-full transition-all ${completed ? "bg-emerald-400" : "bg-amber-400"}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
