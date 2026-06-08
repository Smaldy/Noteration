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

/** The arcade cabinet: a 2.5-D machine with a backlit marquee, a wide CRT, and an
 *  angled control deck. ◄ ► buttons change the on-screen panel; ▲ ▼ pick New
 *  Start / Continue; the lever (with a coin dropping into the slot) starts. */
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

  // A run can't continue what doesn't exist — keep the selection valid.
  useEffect(() => {
    if (selection === "resume" && !canResume) setSelection("fresh");
  }, [selection, canResume]);

  const cycleScreen = useCallback((dir: 1 | -1) => {
    setScreen((s) => {
      const i = SCREENS.indexOf(s);
      return SCREENS[(i + dir + SCREENS.length) % SCREENS.length];
    });
  }, []);

  const cycleSelection = useCallback(() => {
    if (canResume) setSelection((s) => (s === "fresh" ? "resume" : "fresh"));
  }, [canResume]);

  const pull = useCallback(() => {
    if (pulling || onCooldown || !affordable) return;
    setPulling(true);
    // Drop a coin (or a few) into the slot as the lever tips.
    const drops = Math.min(cost, 3);
    setCoins(Array.from({ length: drops }, () => coinId.current++));
    window.setTimeout(async () => {
      const result = await startRun(selection);
      if (!result.ok) {
        setPulling(false);
        setCoins([]);
      }
      // On success the overlay unmounts (phase → starting); no reset needed.
    }, 720);
  }, [pulling, onCooldown, affordable, cost, startRun, selection]);

  // Keyboard play: arrows drive the deck, Enter/Space pulls the lever.
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
          className="arcade-room fixed inset-0 z-[90] flex items-center justify-center overflow-y-auto p-4"
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
            className="arcade-cab relative w-full max-w-xl"
            initial={{ scale: 0.86, y: 28, opacity: 0 }}
            animate={{ scale: 1, y: 0, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", stiffness: 230, damping: 23 }}
          >
            <button
              type="button"
              onClick={close}
              aria-label="Close arcade"
              className="absolute -right-1 -top-1 z-20 grid size-8 place-items-center rounded-full bg-white/10 text-white/70 backdrop-blur transition hover:bg-white/20 hover:text-white"
            >
              <X className="size-4" />
            </button>

            {/* Marquee */}
            <div className={`arcade-marquee mx-auto w-[88%] py-3 text-center ${ARCADE_PIXEL}`}>
              <p className="arcade-marquee-title text-base tracking-[0.18em] sm:text-lg">
                NOTINVASION
              </p>
            </div>

            {/* Screen + neck */}
            <div className="arcade-cab-side mt-[-2px] rounded-t-xl px-5 pb-4 pt-5">
              <div className="arcade-tv mx-auto max-w-md">
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

              {/* Screen dots */}
              <div className="mt-3 flex justify-center gap-2">
                {SCREENS.map((s) => (
                  <span
                    key={s}
                    className={`h-1.5 w-1.5 rounded-full ${screen === s ? "bg-fuchsia-400" : "bg-white/20"}`}
                  />
                ))}
              </div>
            </div>

            {/* Control deck (angled) */}
            <div className="arcade-deck-wrap">
              <div className="arcade-deck grid grid-cols-[auto_1fr_auto] items-center gap-3 px-6 py-5">
                {/* Directional cluster */}
                <DirectionCluster
                  onLeft={() => cycleScreen(-1)}
                  onRight={() => cycleScreen(1)}
                  onUpDown={cycleSelection}
                  resumeEnabled={canResume}
                />

                {/* Coin slot (coins drop in here) */}
                <CoinSlot coins={state?.coins ?? 0} flying={coins} onLanded={(id) =>
                  setCoins((c) => c.filter((x) => x !== id))
                } />

                {/* Start lever */}
                <div className="flex flex-col items-center gap-1">
                  <ArcadeLever pulled={pulling} disabled={onCooldown || !affordable} onPull={pull} />
                  <span className={`text-[6px] ${ARCADE_PIXEL} arcade-dim`}>START</span>
                </div>
              </div>
              <div className="arcade-deck-lip mx-3" />
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
    <div className="grid grid-cols-3 grid-rows-3 gap-1.5">
      <span />
      <ArcadeButton ariaLabel="Select previous option" onClick={onUpDown} disabled={!resumeEnabled} variant="amber">
        <ChevronUp className="size-5" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Previous screen" onClick={onLeft}>
        <ChevronLeft className="size-5" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Next screen" onClick={onRight}>
        <ChevronRight className="size-5" />
      </ArcadeButton>
      <span />
      <ArcadeButton ariaLabel="Select next option" onClick={onUpDown} disabled={!resumeEnabled} variant="amber">
        <ChevronDown className="size-5" />
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
    <div className={`arcade-slot relative mx-auto flex w-full max-w-[150px] flex-col items-center gap-2 px-3 py-2.5 ${ARCADE_PIXEL}`}>
      <span className="arcade-dim text-[7px]">COINS</span>
      <span className="arcade-neon-yellow text-sm">{coins}</span>
      <span className="arcade-slot-mouth" />
      {/* Coins arcing in from the lever side, disappearing into the mouth. */}
      <div className="pointer-events-none absolute bottom-2 left-1/2 -translate-x-1/2">
        {flying.map((id, i) => (
          <motion.span
            key={id}
            className="arcade-coin absolute"
            initial={{ x: 150, y: -90, opacity: 0, scale: 0.5, rotate: 0 }}
            animate={{
              x: [150, 70, 0],
              y: [-90, -120, 4],
              opacity: [0, 1, 1, 0],
              scale: [0.5, 1, 0.55],
              rotate: [0, 220, 420],
            }}
            transition={{ duration: 0.7, delay: i * 0.12, times: [0, 0.45, 1], ease: "easeIn" }}
            onAnimationComplete={() => onLanded(id)}
          >
            ¢
          </motion.span>
        ))}
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
