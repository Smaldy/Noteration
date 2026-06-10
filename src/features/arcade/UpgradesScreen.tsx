import { Lock, Sparkles } from "lucide-react";
import { useEffect, useRef } from "react";

import type { ArcadeState } from "@/types/arcade";

import { ARCADE_PIXEL } from "./crtStyles";

const TIER_LABEL: Record<number, string> = {
  1: "TIER I · CORE",
  2: "TIER II · FIREPOWER",
  3: "TIER III · TACTICAL",
};

/** The shop. Selection is driven by the deck's ▲ ▼ buttons (selectedIndex);
 *  the lever buys the highlighted row. Purely presentational — the overlay owns
 *  the selection and the buy action. */
export function UpgradesScreen({
  state,
  selectedIndex,
  error,
  busy,
}: {
  state: ArcadeState;
  selectedIndex: number;
  error?: string | null;
  busy?: boolean;
}) {
  const selRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    selRef.current?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  return (
    <div className={`flex h-full flex-col ${ARCADE_PIXEL}`}>
      <div className="flex items-center justify-between">
        <p className="arcade-neon-cyan text-[11px] tracking-[0.3em]">STORE</p>
        <p className="text-[9px]">
          <span className="arcade-dim">SCORE </span>
          <span className="arcade-neon-yellow text-sm">{state.score_balance}</span>
        </p>
      </div>

      <div className="mt-2 flex-1 space-y-2 overflow-y-auto pr-1">
        {state.upgrades.map((u, i) => {
          const selected = i === selectedIndex;
          const locked = u.locked;
          const maxed = u.next_cost == null;
          const affordable = !maxed && !locked && state.score_balance >= (u.next_cost ?? 0);
          // Inject a tier header before the first skill of each new tier.
          const newTier = i === 0 || state.upgrades[i - 1].tier !== u.tier;
          return (
            <div key={u.key}>
              {newTier && (
                <p className="arcade-dim mb-1.5 mt-1 text-[7px] tracking-[0.25em] first:mt-0">
                  {TIER_LABEL[u.tier] ?? `TIER ${u.tier}`}
                </p>
              )}
              <div
                ref={selected ? selRef : undefined}
                className={`flex items-center justify-between gap-3 rounded-md border px-3 py-2 transition ${
                  selected
                    ? "border-fuchsia-300/80 bg-fuchsia-500/10"
                    : "border-fuchsia-400/15 bg-black/40"
                } ${locked ? "opacity-55" : ""}`}
              >
                <div className="min-w-0">
                  <p className={`text-[9px] ${selected ? "arcade-neon-cyan" : "arcade-neon-green"}`}>
                    {u.name}
                  </p>
                  <p className="arcade-dim mt-1 truncate text-[7px] leading-relaxed">
                    {u.description}
                  </p>
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {Array.from({ length: u.max_level }, (_, k) => (
                      <span
                        key={k}
                        className={`h-1.5 w-3 rounded-sm ${k < u.level ? "bg-amber-400" : "bg-white/15"}`}
                      />
                    ))}
                  </div>
                </div>

                <div className="shrink-0 text-right">
                  {locked ? (
                    <span className="arcade-neon-pink inline-flex items-center gap-1 text-[8px]">
                      <Lock className="size-2.5" />
                      WAVE {u.unlock_wave}
                    </span>
                  ) : maxed ? (
                    <span className="arcade-neon-yellow text-[8px]">MAX</span>
                  ) : busy && selected ? (
                    <span className="arcade-neon-cyan arcade-blink text-[8px]">BUYING</span>
                  ) : (
                    <span
                      className={`inline-flex items-center gap-1 text-[8px] ${
                        affordable ? "arcade-neon-yellow" : "arcade-dim"
                      }`}
                    >
                      <Sparkles className="size-3" />
                      {u.next_cost}
                    </span>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <p className="mt-2 text-center text-[7px]">
        {error ? (
          <span className="arcade-neon-pink">{error}</span>
        ) : (
          <span className="arcade-dim">▲▼ SELECT · PULL LEVER TO BUY</span>
        )}
      </p>
    </div>
  );
}
