import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronLeft, ChevronRight, ChevronUp, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState } from "@/types/arcade";

import { ArcadeButton } from "./ArcadeButton";
import { ArcadeLever } from "./ArcadeLever";
import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { MainScreen, type StartMode } from "./MainScreen";
import { QuestsScreen } from "./QuestsScreen";
import { UpgradesScreen } from "./UpgradesScreen";

type Screen = "main" | "store" | "quests";
const SCREENS: Screen[] = ["main", "store", "quests"];

/** The arcade cabinet: a faux-3-D machine with an extruded marquee, a wide CRT,
 *  an angled button deck, a front-bottom coin slot, and a casino pull lever on
 *  the right side. ◄ ► change the on-screen panel; ▲ ▼ pick New Start / Continue;
 *  the lever drops a coin into the slot and starts. */
export function ArcadeOverlay() {
  const open = useArcadeStore((s) => s.overlayOpen);
  const close = useArcadeStore((s) => s.closeOverlay);
  const status = useArcadeStore((s) => s.status);
  const state = useArcadeStore((s) => s.state);
  const startRun = useArcadeStore((s) => s.startRun);

  const [screen, setScreen] = useState<Screen>("main");
  const [selection, setSelection] = useState<StartMode>("fresh");
  const [pulling, setPulling] = useState(false);
  const [coins, setCoins] = useState<number[]>([]);
  const coinId = useRef(0);

  const canResume = !!state && state.resumable_wave > 0 && state.resume_cost != null;
  const onCooldown =
    !!state?.cooldown_until && new Date(state.cooldown_until).getTime() > Date.now();
  const cost =
    selection === "resume" ? (state?.resume_cost ?? 0) : (state?.economy.base_cost ?? 0);
  const affordable =
    !!state && state.coins >= cost && (selection !== "resume" || canResume);

  useEffect(() => {
    if (selection === "resume" && !canResume) setSelection("fresh");
  }, [selection, canResume]);

  const cycleScreen = useCallback((dir: 1 | -1) => {
    setScreen((s) => SCREENS[(SCREENS.indexOf(s) + dir + SCREENS.length) % SCREENS.length]);
  }, []);

  const cycleSelection = useCallback(() => {
    if (canResume) setSelection((s) => (s === "fresh" ? "resume" : "fresh"));
  }, [canResume]);

  const pull = useCallback(() => {
    if (pulling || onCooldown || !affordable) return;
    setPulling(true);
    const drops = Math.min(cost, 3);
    setCoins(Array.from({ length: drops }, () => coinId.current++));
    window.setTimeout(async () => {
      const result = await startRun(selection);
      if (!result.ok) {
        setPulling(false);
        setCoins([]);
      }
    }, 760);
  }, [pulling, onCooldown, affordable, cost, startRun, selection]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") cycleScreen(-1);
      else if (e.key === "ArrowRight") cycleScreen(1);
      else if (e.key === "ArrowUp" || e.key === "ArrowDown") cycleSelection();
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pull();
      } else if (e.key === "Escape") close();
      else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, cycleScreen, cycleSelection, pull, close]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="arcade-room fixed inset-0 z-[90] flex items-center justify-center overflow-y-auto p-6"
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
            className="arcade-cab relative my-auto w-full max-w-2xl"
            initial={{ scale: 0.86, y: 28, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", stiffness: 230, damping: 23 }}
          >
            <button
              type="button"
              onClick={close}
              aria-label="Close arcade"
              className="absolute -right-2 -top-2 z-30 grid size-8 place-items-center rounded-full bg-white/10 text-white/70 backdrop-blur transition hover:bg-white/20 hover:text-white"
            >
              <X className="size-4" />
            </button>

            {/* Casino pull lever on the right wall */}
            <div className="absolute -right-9 top-[34%] z-20">
              <ArcadeLever pulled={pulling} disabled={onCooldown || !affordable} onPull={pull} />
              <p className={`mt-1 text-center text-[7px] ${ARCADE_PIXEL} arcade-dim`}>START</p>
            </div>

            {/* Marquee (extruded block) */}
            <div className={`arcade-marquee mx-auto w-[84%] py-3.5 text-center ${ARCADE_PIXEL}`}>
              <p className="arcade-marquee-title text-lg tracking-[0.18em] sm:text-2xl">
                NOTINVASION
              </p>
            </div>

            {/* Screen section */}
            <div className="arcade-cab-side mt-3 rounded-t-2xl px-6 pb-5 pt-6">
              <div className="arcade-tv mx-auto max-w-lg">
                <div className="arcade-screen">
                  <div className="arcade-screen-inner">
                    {state == null ? (
                      <LoadingScreen status={status} />
                    ) : (
                      <AnimatePresence mode="wait">
                        <motion.div
                          key={screen}
                          className="h-full"
                          initial={{ opacity: 0, x: 22 }}
                          animate={{ opacity: 1, x: 0 }}
                          exit={{ opacity: 0, x: -22 }}
                          transition={{ duration: 0.18 }}
                        >
                          <ScreenBody screen={screen} state={state} selection={selection} />
                        </motion.div>
                      </AnimatePresence>
                    )}
                  </div>
                </div>
              </div>

              <div className="mt-3 flex justify-center gap-2">
                {SCREENS.map((s) => (
                  <span
                    key={s}
                    className={`h-1.5 w-1.5 rounded-full ${screen === s ? "bg-fuchsia-400" : "bg-white/20"}`}
                  />
                ))}
              </div>
            </div>

            {/* Control deck — directional buttons only */}
            <div className="arcade-deck-wrap">
              <div className="arcade-deck flex justify-center px-6 py-6">
                <DirectionCluster
                  onLeft={() => cycleScreen(-1)}
                  onRight={() => cycleScreen(1)}
                  onUpDown={cycleSelection}
                  resumeEnabled={canResume}
                />
              </div>
            </div>

            {/* Front-bottom base — coin slot */}
            <div className="arcade-base flex justify-center px-6 py-5">
              <CoinSlot
                coins={state?.coins ?? 0}
                flying={coins}
                onLanded={(id) => setCoins((c) => c.filter((x) => x !== id))}
              />
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

function ScreenBody({
  screen,
  state,
  selection,
}: {
  screen: Screen;
  state: ArcadeState;
  selection: StartMode;
}) {
  if (screen === "store") return <UpgradesScreen state={state} />;
  if (screen === "quests") return <QuestsScreen state={state} />;
  return <MainScreen state={state} selection={selection} />;
}

function DirectionCluster({
  onLeft,
  onRight,
  onUpDown,
  resumeEnabled,
}: {
  onLeft: () => void;
  onRight: () => void;
  onUpDown: () => void;
  resumeEnabled: boolean;
}) {
  return (
    <div className="grid grid-cols-3 grid-rows-3 gap-2">
      <span />
      <ArcadeButton ariaLabel="Select previous option" onClick={onUpDown} disabled={!resumeEnabled}>
        <ChevronUp className="size-6" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Previous screen" onClick={onLeft}>
        <ChevronLeft className="size-6" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Next screen" onClick={onRight}>
        <ChevronRight className="size-6" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Select next option" onClick={onUpDown} disabled={!resumeEnabled}>
        <ChevronDown className="size-6" />
      </ArcadeButton>
      <span />
    </div>
  );
}

function CoinSlot({
  coins,
  flying,
  onLanded,
}: {
  coins: number;
  flying: number[];
  onLanded: (id: number) => void;
}) {
  return (
    <div className={`arcade-slot relative flex w-full max-w-[220px] items-center justify-between gap-3 px-4 py-3 ${ARCADE_PIXEL}`}>
      <div className="flex flex-col">
        <span className="arcade-dim text-[7px]">COINS</span>
        <span className="arcade-neon-yellow text-base">{coins}</span>
      </div>
      <div className="relative">
        <span className="arcade-slot-mouth block" />
        {/* Coins arcing in from the upper-right (lever), into the mouth. */}
        <div className="pointer-events-none absolute left-1/2 top-1/2">
          {flying.map((id, i) => (
            <motion.span
              key={id}
              className="arcade-coin absolute -translate-x-1/2 -translate-y-1/2"
              initial={{ x: 190, y: -200, opacity: 0, scale: 0.5, rotate: 0 }}
              animate={{
                x: [190, 80, 0],
                y: [-200, -150, 2],
                opacity: [0, 1, 1, 0],
                scale: [0.5, 1, 0.5],
                rotate: [0, 240, 460],
              }}
              transition={{ duration: 0.74, delay: i * 0.12, times: [0, 0.5, 1], ease: "easeIn" }}
              onAnimationComplete={() => onLanded(id)}
            >
              ¢
            </motion.span>
          ))}
        </div>
      </div>
    </div>
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
