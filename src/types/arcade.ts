/** Mirrors backend/schemas/arcade.py — the study-gated minigame's state. */

export interface ArcadeUpgrade {
  key: string;
  name: string;
  description: string;
  level: number;
  max_level: number;
  next_cost: number | null;
  tier: number; // 1..5 — skills are grouped and gated by tier
  unlock_wave: number; // wave_record needed to buy this tier (0 = always open)
  locked: boolean; // true while wave_record < unlock_wave
}

export interface DailyQuest {
  mcq_count: number;
  target: number;
  bonus_claimed: boolean;
  completed: boolean;
}

export interface ArcadeEconomy {
  coin_per_flashcard: number;
  coin_per_mcq: number;
  base_cost: number;
}

export interface ArcadeState {
  coins: number;
  score_balance: number;
  high_score: number;
  wave_record: number;
  resumable_wave: number;
  resumable_score: number;
  resume_cost: number | null;
  resume_count: number; // continues used on the current run lineage
  max_continues: number; // continues allowed before a forced fresh start
  cooldown_until: string | null; // ISO datetime
  daily_quest: DailyQuest;
  upgrades: ArcadeUpgrade[];
  economy: ArcadeEconomy;
  // Prestige / special bullets (tier 6).
  prestige_count: number;
  can_prestige: boolean; // final tier reached → a prestige is allowed
  prestige_unlock_wave: number; // wave_record needed to prestige
  active_special: string; // "none" | "electric" | "love"
  specials: string[]; // selectable special-bullet ids
}

export interface RunStart {
  session_id: number;
  start_wave: number;
  start_score: number;
  cost: number;
  coins_after: number;
}

/** Owned upgrade levels keyed by upgrade key — convenience for the game engine. */
export type UpgradeLevels = Record<string, number>;

export function upgradeLevels(state: ArcadeState | null): UpgradeLevels {
  const out: UpgradeLevels = {};
  for (const u of state?.upgrades ?? []) out[u.key] = u.level;
  return out;
}
