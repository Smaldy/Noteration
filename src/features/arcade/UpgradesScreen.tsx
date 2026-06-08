import { motion } from "framer-motion";
import { Sparkles } from "lucide-react";
import { useState } from "react";

import { useArcadeStore } from "@/stores/arcade";
import type { ArcadeState, ArcadeUpgrade } from "@/types/arcade";

import { ARCADE_PIXEL } from "./crtStyles";

/** The shop: spend score points (earned during runs) on permanent upgrades. */
export function UpgradesScreen({ state }: { state: ArcadeState }) {
  const buyUpgrade = useArcadeStore((s) => s.buyUpgrade);
  const [error, setError] = useState<string | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  async function buy(key: string) {
    setError(null);
    setBusyKey(key);
    const result = await buyUpgrade(key);
    if (!result.ok) setError(result.error ?? "Could not buy");
    setBusyKey(null);
  }

  return (
    <div className={`flex h-full flex-col py-5 ${ARCADE_PIXEL}`}>
      <div className="text-center">
        <p className="arcade-neon-cyan text-[11px] tracking-[0.3em]">UPGRADES</p>
        <p className="mt-3 text-[9px]">
          <span className="arcade-dim">SCORE </span>
          <span className="arcade-neon-yellow text-sm">{state.score_balance}</span>
        </p>
      </div>

      <div className="mt-4 flex-1 space-y-2 overflow-y-auto pr-1">
        {state.upgrades.map((u) => (
          <UpgradeRow
            key={u.key}
            upgrade={u}
            affordable={u.next_cost != null && state.score_balance >= u.next_cost}
            busy={busyKey === u.key}
            onBuy={() => buy(u.key)}
          />
        ))}
      </div>

      {error && <p className="arcade-neon-pink mt-2 text-center text-[8px]">{error}</p>}
    </div>
  );
}

function UpgradeRow({
  upgrade,
  affordable,
  busy,
  onBuy,
}: {
  upgrade: ArcadeUpgrade;
  affordable: boolean;
  busy: boolean;
  onBuy: () => void;
}) {
  const maxed = upgrade.next_cost == null;
  return (
    <div className="flex items-center justify-between gap-3 rounded-md border border-fuchsia-400/20 bg-black/40 px-3 py-2">
      <div className="min-w-0">
        <p className="arcade-neon-green text-[9px]">{upgrade.name}</p>
        <p className="arcade-dim mt-1 truncate text-[7px] leading-relaxed">
          {upgrade.description}
        </p>
        <div className="mt-1.5 flex gap-1">
          {Array.from({ length: upgrade.max_level }, (_, i) => (
            <span
              key={i}
              className={`h-1.5 w-3 rounded-sm ${
                i < upgrade.level ? "bg-amber-400" : "bg-white/15"
              }`}
            />
          ))}
        </div>
      </div>

      {maxed ? (
        <span className="arcade-neon-yellow shrink-0 text-[8px]">MAX</span>
      ) : (
        <motion.button
          type="button"
          onClick={onBuy}
          disabled={!affordable || busy}
          whileTap={affordable ? { scale: 0.9 } : undefined}
          className={`flex shrink-0 flex-col items-center gap-0.5 rounded border px-2.5 py-1.5 text-[7px] transition disabled:opacity-50 ${
            affordable ? "border-amber-400/60 arcade-neon-yellow" : "border-white/15 arcade-dim"
          }`}
        >
          <Sparkles className="size-3" />
          <span>{upgrade.next_cost}</span>
        </motion.button>
      )}
    </div>
  );
}
