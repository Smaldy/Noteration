import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState } from "@/types/arcade";

import { CabinetStage } from "./CabinetStage";
import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { MainScreen, type StartMode } from "./MainScreen";
import { QuestsScreen } from "./QuestsScreen";
import { UpgradesScreen } from "./UpgradesScreen";

type Screen = "main" | "store" | "quests";
const SCREENS: Screen[] = ["main", "store", "quests"];

/** The arcade cabinet, authored as a coordinate blockout (cabinetLayout.ts).
 *  ◄ ► change the on-screen panel; ▲ ▼ pick New Start / Continue; the side lever
 *  drops a coin into the slot and starts. Press **B** to toggle the red blockout
 *  for tuning part proportions. */
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
  const [block, setBlock] = useState(false);
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
      else if (e.key === "b" || e.key === "B") setBlock((b) => !b);
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pull();
      } else if (e.key === "Escape") close();
      else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, cycleScreen, cycleSelection, pull, close]);

  const screenContent =
    state == null ? (
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
    );

  const dots = SCREENS.map((s) => (
    <span
      key={s}
      className={`h-1.5 w-1.5 rounded-full ${screen === s ? "bg-fuchsia-400" : "bg-white/20"}`}
    />
  ));

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

          <button
            type="button"
            onClick={close}
            aria-label="Close arcade"
            className="absolute right-4 top-4 z-30 grid size-9 place-items-center rounded-full bg-white/10 text-white/70 backdrop-blur transition hover:bg-white/20 hover:text-white"
          >
            <X className="size-5" />
          </button>

          <button
            type="button"
            onClick={() => setBlock((b) => !b)}
            className={`absolute left-4 top-4 z-30 rounded-full px-3 py-1.5 text-[10px] font-bold tracking-wider backdrop-blur transition ${
              block
                ? "bg-red-500/80 text-white"
                : "bg-white/10 text-white/60 hover:bg-white/20"
            }`}
          >
            BLOCKOUT (B): {block ? "ON" : "OFF"}
          </button>

          <motion.div
            className="relative my-auto"
            initial={{ scale: 0.9, opacity: 0 }}
            animate={{ scale: 1, opacity: 1 }}
            exit={{ scale: 0.92, opacity: 0 }}
            transition={{ type: "spring", stiffness: 220, damping: 24 }}
          >
            <CabinetStage
              block={block}
              screen={screenContent}
              screenDots={dots}
              marquee="NOTINVASION"
              canResume={canResume}
              onCycleScreen={cycleScreen}
              onCycleSelection={cycleSelection}
              leverPulled={pulling}
              leverDisabled={onCooldown || !affordable}
              onPull={pull}
              coinsCount={state?.coins ?? 0}
              flyingCoins={coins}
              onCoinLanded={(id) => setCoins((c) => c.filter((x) => x !== id))}
            />
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

function LoadingScreen({ status }: { status: string }) {
  return (
    <div className={`flex h-full items-center justify-center ${ARCADE_PIXEL}`}>
      <p className="arcade-neon-cyan arcade-blink text-[10px]">
        {status === "error" ? "NO SIGNAL" : "LOADING..."}
      </p>
    </div>
  );
}
