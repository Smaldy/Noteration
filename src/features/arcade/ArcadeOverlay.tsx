import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  ChevronUp,
  X,
} from "lucide-react";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState } from "@/types/arcade";

import { ArcadeLever } from "./ArcadeLever";
import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { MainScreen, type StartMode } from "./MainScreen";
import { QuestsScreen } from "./QuestsScreen";
import { UpgradesScreen } from "./UpgradesScreen";

type Screen = "main" | "store" | "quests";
const SCREENS: Screen[] = ["main", "store", "quests"];

/** The arcade cabinet, built from real 3D planes (perspective + preserve-3d):
 *  a marquee, a recessed CRT, a slanted button deck, and a coin base. ◄ ► change
 *  the on-screen panel; ▲ ▼ pick New Start / Continue; the side lever drops a coin
 *  into the slot and starts. */
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
          className="arcade-room fixed inset-0 z-[90] flex items-center justify-center overflow-y-auto p-8"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.3 }}
          role="dialog"
          aria-modal="true"
          aria-label="Arcade machine"
        >
          <style>{arcadeStyles}</style>

          {/* Fade/scale wrapper kept free of preserve-3d so the cabinet's own 3D
              planes render cleanly. */}
          <motion.div
            className="relative my-auto"
            initial={{ scale: 0.85, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.9, opacity: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 24 }}
          >
            <button
              type="button"
              onClick={close}
              aria-label="Close arcade"
              className="absolute -right-2 -top-12 z-30 grid size-9 place-items-center rounded-full bg-white/10 text-white/70 backdrop-blur transition hover:bg-white/20 hover:text-white"
            >
              <X className="size-5" />
            </button>

            <div className="arcade-scene">
              <div className="cabinet-body">
                {/* Marquee */}
                <div className="box-marquee">
                  <h1 className={`marquee-text ${ARCADE_PIXEL} tracking-[0.16em]`}>
                    NOTINVASION
                  </h1>
                </div>

                {/* Screen housing + side lever */}
                <div className="box-screen-housing">
                  <div className="crt-screen">
                    <div className="arcade-screen-inner">
                      {state == null ? (
                        <LoadingScreen status={status} />
                      ) : (
                        <AnimatePresence mode="wait">
                          <motion.div
                            key={screen}
                            className="h-full"
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            exit={{ opacity: 0, x: -20 }}
                            transition={{ duration: 0.18 }}
                          >
                            <ScreenBody screen={screen} state={state} selection={selection} />
                          </motion.div>
                        </AnimatePresence>
                      )}
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

                  <ArcadeLever
                    pulled={pulling}
                    disabled={onCooldown || !affordable}
                    onPull={pull}
                  />
                </div>

                {/* Control deck */}
                <div className="box-control-deck">
                  <DeckButton mod="left" ariaLabel="Previous screen" onClick={() => cycleScreen(-1)}>
                    <ChevronLeft className="size-5" />
                  </DeckButton>
                  <DeckButton mod="top" ariaLabel="Select previous" onClick={cycleSelection} disabled={!canResume}>
                    <ChevronUp className="size-5" />
                  </DeckButton>
                  <DeckButton mod="bottom" ariaLabel="Select next" onClick={cycleSelection} disabled={!canResume}>
                    <ChevronDown className="size-5" />
                  </DeckButton>
                  <DeckButton mod="right" ariaLabel="Next screen" onClick={() => cycleScreen(1)}>
                    <ChevronRight className="size-5" />
                  </DeckButton>
                </div>

                {/* Coin base */}
                <div className="box-coin-base">
                  <CoinSlot
                    coins={state?.coins ?? 0}
                    flying={coins}
                    onLanded={(id) => setCoins((c) => c.filter((x) => x !== id))}
                  />
                </div>
              </div>
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

function DeckButton({
  mod,
  ariaLabel,
  onClick,
  disabled,
  children,
}: {
  mod: string;
  ariaLabel: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      className={`deck-btn ${mod}`}
      aria-label={ariaLabel}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
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
    <div className={`coin-slot ${ARCADE_PIXEL}`}>
      <div className="flex flex-col">
        <span className="arcade-dim text-[7px]">COINS</span>
        <span className="arcade-neon-yellow text-base">{coins}</span>
      </div>
      <div className="relative">
        <span className="arcade-slot-mouth block" />
        <div className="pointer-events-none absolute left-1/2 top-1/2">
          {flying.map((id, i) => (
            <motion.span
              key={id}
              className="arcade-coin absolute -translate-x-1/2 -translate-y-1/2"
              initial={{ x: 170, y: -210, opacity: 0, scale: 0.5, rotate: 0 }}
              animate={{
                x: [170, 70, 0],
                y: [-210, -150, 2],
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
