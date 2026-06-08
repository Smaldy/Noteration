/**
 * Renders the cabinet from CABINET_PARTS onto a fixed design stage that scales
 * to fit the viewport. Decorative parts draw as primitives; the FUNCTIONAL_SLOTS
 * (screen, deck buttons, lever, coin slot) draw the live interactive element at
 * the same coordinates. Pass `block` to flip everything to the red blockout.
 */
import { motion } from "framer-motion";
import { type ReactNode, useEffect, useState } from "react";

import {
  CABINET_PARTS,
  FUNCTIONAL_SLOTS,
  partById,
  STAGE_H,
  STAGE_W,
} from "./cabinetLayout";
import { partBox, Primitive } from "./primitives";

const LEVER_REST = -35; // deg — stick resting up
const LEVER_PULL = 26; // deg — yanked down

export interface CabinetStageProps {
  block: boolean;
  /** content rendered inside the CRT (menu / loading). */
  screen: ReactNode;
  /** dots/indicator strip under the screen. */
  screenDots: ReactNode;
  /** the marquee title. */
  marquee: ReactNode;
  canResume: boolean;
  onCycleScreen: (dir: 1 | -1) => void;
  onCycleSelection: () => void;
  leverPulled: boolean;
  leverDisabled: boolean;
  onPull: () => void;
  coinsCount: number;
  flyingCoins: number[];
  onCoinLanded: (id: number) => void;
}

function useFitScale() {
  const [scale, setScale] = useState(1);
  useEffect(() => {
    const fit = () => {
      const s = Math.min(
        (window.innerWidth * 0.9) / STAGE_W,
        (window.innerHeight * 0.86) / STAGE_H,
      );
      setScale(Math.min(s, 1.1));
    };
    fit();
    window.addEventListener("resize", fit);
    return () => window.removeEventListener("resize", fit);
  }, []);
  return scale;
}

export function CabinetStage(props: CabinetStageProps) {
  const scale = useFitScale();
  const screenPart = partById("screen");

  return (
    <div
      className="cab-scaler"
      style={{ width: STAGE_W * scale, height: STAGE_H * scale }}
    >
      <div
        className="cab-stage"
        style={{ width: STAGE_W, height: STAGE_H, transform: `scale(${scale})` }}
      >
        {CABINET_PARTS.map((p) => {
          if (props.block || !FUNCTIONAL_SLOTS.has(p.id)) {
            return (
              <Primitive key={p.id} part={p} block={props.block}>
                {!props.block && p.id === "marquee" ? (
                  <span className="marquee-text arcade-pixel">{props.marquee}</span>
                ) : null}
              </Primitive>
            );
          }
          return renderSlot(p.id, props);
        })}

        {/* screen indicator dots, parked just under the screen box */}
        {!props.block && screenPart && (
          <div
            style={{
              position: "absolute",
              left: screenPart.x,
              top: screenPart.y + screenPart.h + 6,
              width: screenPart.w,
              zIndex: 7,
            }}
            className="flex justify-center gap-2"
          >
            {props.screenDots}
          </div>
        )}
      </div>
    </div>
  );
}

function renderSlot(id: string, props: CabinetStageProps): ReactNode {
  const p = partById(id);
  if (!p) return null;
  const box = partBox(p);

  switch (id) {
    case "screen":
      return (
        <div key={id} style={box} className="crt-screen">
          <div className="arcade-screen-inner">{props.screen}</div>
        </div>
      );
    case "btn-left":
      return (
        <DeckButton key={id} box={box} label="Previous screen" onClick={() => props.onCycleScreen(-1)}>
          ◄
        </DeckButton>
      );
    case "btn-right":
      return (
        <DeckButton key={id} box={box} label="Next screen" onClick={() => props.onCycleScreen(1)}>
          ►
        </DeckButton>
      );
    case "btn-up":
      return (
        <DeckButton
          key={id}
          box={box}
          label="Select previous"
          onClick={props.onCycleSelection}
          disabled={!props.canResume}
        >
          ▲
        </DeckButton>
      );
    case "btn-down":
      return (
        <DeckButton
          key={id}
          box={box}
          label="Select next"
          onClick={props.onCycleSelection}
          disabled={!props.canResume}
        >
          ▼
        </DeckButton>
      );
    case "lever":
      return (
        <Lever
          key={id}
          box={box}
          pulled={props.leverPulled}
          disabled={props.leverDisabled}
          onPull={props.onPull}
        />
      );
    case "coin-slot":
      return (
        <CoinSlot
          key={id}
          box={box}
          coins={props.coinsCount}
          flying={props.flyingCoins}
          onLanded={props.onCoinLanded}
        />
      );
    default:
      return null;
  }
}

function DeckButton({
  box,
  label,
  onClick,
  disabled,
  children,
}: {
  box: React.CSSProperties;
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      style={box}
      className="cab-btn"
      aria-label={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

function Lever({
  box,
  pulled,
  disabled,
  onPull,
}: {
  box: React.CSSProperties;
  pulled: boolean;
  disabled?: boolean;
  onPull: () => void;
}) {
  return (
    <button
      type="button"
      style={box}
      onClick={onPull}
      disabled={disabled}
      aria-label="Pull the lever to start"
      className={`cab-lever ${disabled ? "is-disabled" : ""}`}
    >
      <span className="cab-lever-base" />
      <motion.span
        className="cab-lever-arm"
        initial={{ rotate: LEVER_REST }}
        animate={{ rotate: pulled ? [LEVER_REST, LEVER_PULL, LEVER_REST] : LEVER_REST }}
        transition={{ duration: 0.66, ease: [0.34, 1.56, 0.64, 1], times: [0, 0.42, 1] }}
      >
        <span className="cab-lever-stick" />
        <span className="cab-lever-ball" />
      </motion.span>
    </button>
  );
}

function CoinSlot({
  box,
  coins,
  flying,
  onLanded,
}: {
  box: React.CSSProperties;
  coins: number;
  flying: number[];
  onLanded: (id: number) => void;
}) {
  return (
    <div style={box} className="coin-slot arcade-pixel">
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
              initial={{ x: 150, y: -210, opacity: 0, scale: 0.5, rotate: 0 }}
              animate={{
                x: [150, 60, 0],
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
