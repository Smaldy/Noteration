import { Coins, Target } from "lucide-react";

import type { ArcadeState } from "@/types/arcade";

import { ARCADE_PIXEL } from "./crtStyles";

/** The CRT's quests screen: the daily MCQ quest + lifetime stats. Reached with
 *  the ◄ ► deck buttons. */
export function QuestsScreen({ state }: { state: ArcadeState }) {
  const { mcq_count, target, completed } = state.daily_quest;
  const pct = Math.min(100, (mcq_count / target) * 100);

  return (
    <div className={`flex h-full flex-col ${ARCADE_PIXEL}`}>
      <p className="arcade-neon-cyan text-center text-[11px] tracking-[0.3em]">QUESTS</p>

      <div className="mt-4 rounded-md border border-fuchsia-400/25 bg-black/40 p-3">
        <div className="flex items-center gap-2">
          <Target className="size-3.5 text-fuchsia-300" />
          <p className="arcade-neon-green text-[8px]">DAILY · {target} CORRECT MCQ</p>
        </div>
        <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-white/10">
          <div
            className={`h-full transition-all ${completed ? "bg-emerald-400" : "bg-amber-400"}`}
            style={{ width: `${pct}%` }}
          />
        </div>
        <div className="mt-2 flex items-center justify-between text-[8px]">
          <span className="arcade-dim">{mcq_count}/{target}</span>
          <span className={completed ? "arcade-neon-green" : "arcade-neon-yellow"}>
            {completed ? "CLAIMED +3 ✓" : "REWARD +3 COINS"}
          </span>
        </div>
      </div>

      <div className="mt-auto grid grid-cols-2 gap-2 text-center text-[8px]">
        <Stat icon={<Coins className="size-3 text-amber-300" />} label="COINS" value={state.coins} tone="yellow" />
        <Stat label="SCORE" value={state.score_balance} tone="cyan" />
      </div>
      <p className="arcade-dim mt-3 text-center text-[7px]">◄ ► CHANGE SCREEN</p>
    </div>
  );
}

function Stat({
  icon,
  label,
  value,
  tone,
}: {
  icon?: React.ReactNode;
  label: string;
  value: number;
  tone: "yellow" | "cyan";
}) {
  return (
    <div className="rounded-md border border-white/10 bg-black/30 py-2">
      <div className="flex items-center justify-center gap-1">
        {icon}
        <span className="arcade-dim">{label}</span>
      </div>
      <p className={`mt-1 text-sm arcade-neon-${tone}`}>{value}</p>
    </div>
  );
}
