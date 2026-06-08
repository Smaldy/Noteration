import { AnimatePresence, motion } from "framer-motion";
import { Timer, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState } from "@/types/arcade";

import { CabinetStage } from "./CabinetStage";
import { ARCADE_PIXEL, arcadeStyles } from "./crtStyles";
import { MainScreen, type StartMode } from "./MainScreen";
import { QuestsScreen } from "./QuestsScreen";
import { UpgradesScreen } from "./UpgradesScreen";
import { useCountdown } from "./useCountdown";

type Screen = "main" | "store" | "quests";
const SCREENS: Screen[] = ["main", "store", "quests"];

/** The arcade cabinet hub. The deck controls are screen-aware:
 *   ◄ ►  always change the on-screen panel.
 *   ▲ ▼  MAIN: pick New Start / Continue · STORE: move the upgrade selection.
 *   lever MAIN: start the selected run (drops coins) · STORE: buy the selected
 *         upgrade. Disabled (with reason) on cooldown / when unaffordable.
 *  Press **B** to toggle the blockout. */
export function ArcadeOverlay() {
  const open = useArcadeStore((s) => s.overlayOpen);
  const close = useArcadeStore((s) => s.closeOverlay);
  const status = useArcadeStore((s) => s.status);
  const state = useArcadeStore((s) => s.state);
  const startRun = useArcadeStore((s) => s.startRun);
  const buyUpgrade = useArcadeStore((s) => s.buyUpgrade);

  const [screen, setScreen] = useState<Screen>("main");
  const [selection, setSelection] = useState<StartMode>("fresh");
  const [storeIdx, setStoreIdx] = useState(0);
  const [storeBusy, setStoreBusy] = useState(false);
  const [storeError, setStoreError] = useState<string | null>(null);
  const [pulling, setPulling] = useState(false);
  const [coins, setCoins] = useState<number[]>([]);
  const [block, setBlock] = useState(false);
  const coinId = useRef(0);

  const cooldown = useCountdown(state?.cooldown_until ?? null);

  const canResume = !!state && state.resumable_wave > 0 && state.resume_cost != null;
  const cost =
    selection === "resume" ? (state?.resume_cost ?? 0) : (state?.economy.base_cost ?? 0);
  const affordable =
    !!state && state.coins >= cost && (selection !== "resume" || canResume);

  const upgrades = state?.upgrades ?? [];
  const selUpgrade = screen === "store" ? upgrades[storeIdx] : undefined;
  const canBuy =
    !!selUpgrade &&
    selUpgrade.next_cost != null &&
    !!state &&
    state.score_balance >= selUpgrade.next_cost;

  // The lever's job (and whether it's allowed) depends on the active screen.
  const leverDisabled =
    screen === "store"
      ? !canBuy || storeBusy
      : screen === "quests"
        ? true
        : cooldown.active || !affordable;

  // ▲ ▼ does something only on MAIN (if there's a resume) and STORE (if >1 item).
  const navEnabled =
    screen === "store" ? upgrades.length > 1 : screen === "main" ? canResume : false;

  // Reset transient lever/store state every time the cabinet (re)opens, so the
  // lever works again after a run instead of staying stuck "pulled".
  useEffect(() => {
    if (!open) return;
    setPulling(false);
    setCoins([]);
    setStoreBusy(false);
    setStoreError(null);
  }, [open]);

  useEffect(() => {
    if (selection === "resume" && !canResume) setSelection("fresh");
  }, [selection, canResume]);

  useEffect(() => {
    const n = upgrades.length;
    setStoreIdx((i) => (n === 0 ? 0 : Math.min(i, n - 1)));
  }, [upgrades.length]);

  const cycleScreen = useCallback((dir: 1 | -1) => {
    setScreen((s) => SCREENS[(SCREENS.indexOf(s) + dir + SCREENS.length) % SCREENS.length]);
    setStoreError(null);
  }, []);

  const moveSelection = useCallback(
    (dir: 1 | -1) => {
      setScreen((s) => {
        if (s === "main") {
          if (canResume) setSelection((m) => (m === "fresh" ? "resume" : "fresh"));
        } else if (s === "store") {
          const n = upgrades.length;
          if (n > 0) setStoreIdx((i) => (i + dir + n) % n);
        }
        return s;
      });
    },
    [canResume, upgrades.length],
  );

  const buySelected = useCallback(async () => {
    const up = state?.upgrades[storeIdx];
    if (!up || up.next_cost == null || !state || state.score_balance < up.next_cost) return;
    setPulling(true);
    setStoreBusy(true);
    setStoreError(null);
    window.setTimeout(() => setPulling(false), 680);
    const res = await buyUpgrade(up.key);
    if (!res.ok) setStoreError(res.error ?? "Can't buy");
    setStoreBusy(false);
  }, [state, storeIdx, buyUpgrade]);

  const startSelected = useCallback(() => {
    if (cooldown.active || !affordable) return;
    setPulling(true);
    const drops = Math.min(cost, 3);
    setCoins(Array.from({ length: drops }, () => coinId.current++));
    window.setTimeout(async () => {
      await startRun(selection);
      // On success the cabinet closes; either way clear the lever so it's ready.
      setPulling(false);
      setCoins([]);
    }, 760);
  }, [cooldown.active, affordable, cost, startRun, selection]);

  const pull = useCallback(() => {
    if (pulling) return;
    if (screen === "store") {
      if (canBuy && !storeBusy) void buySelected();
    } else if (screen === "main") {
      startSelected();
    }
  }, [pulling, screen, canBuy, storeBusy, buySelected, startSelected]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "ArrowLeft") cycleScreen(-1);
      else if (e.key === "ArrowRight") cycleScreen(1);
      else if (e.key === "ArrowUp") moveSelection(-1);
      else if (e.key === "ArrowDown") moveSelection(1);
      else if (e.key === "b" || e.key === "B") setBlock((b) => !b);
      else if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        pull();
      } else if (e.key === "Escape") close();
      else return;
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, cycleScreen, moveSelection, pull, close]);

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
          <ScreenBody
            screen={screen}
            state={state}
            selection={selection}
            storeIdx={storeIdx}
            storeError={storeError}
            storeBusy={storeBusy}
          />
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
              block ? "bg-red-500/80 text-white" : "bg-white/10 text-white/60 hover:bg-white/20"
            }`}
          >
            BLOCKOUT (B): {block ? "ON" : "OFF"}
          </button>

          {/* Always-visible cooldown indicator. */}
          {cooldown.active && (
            <div
              className={`absolute left-1/2 top-4 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full border border-rose-400/50 bg-rose-500/20 px-3 py-1.5 text-[10px] tracking-wider text-rose-100 backdrop-blur ${ARCADE_PIXEL}`}
            >
              <Timer className="size-3.5" />
              COOLDOWN {cooldown.label}
            </div>
          )}

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
              navEnabled={navEnabled}
              onCycleScreen={cycleScreen}
              onMove={moveSelection}
              leverPulled={pulling}
              leverDisabled={leverDisabled}
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
  storeIdx,
  storeError,
  storeBusy,
}: {
  screen: Screen;
  state: ArcadeState;
  selection: StartMode;
  storeIdx: number;
  storeError: string | null;
  storeBusy: boolean;
}) {
  if (screen === "store")
    return (
      <UpgradesScreen
        state={state}
        selectedIndex={storeIdx}
        error={storeError}
        busy={storeBusy}
      />
    );
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
