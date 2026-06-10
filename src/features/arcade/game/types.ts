/**
 * NOTINVASION — game simulation types. Pure data + a single palette; no React,
 * no canvas, no DOM. The world is a plain mutable struct stepped each frame by
 * `world.ts` and drawn by `render.ts`, so the whole sim stays unit-testable.
 */
import type { ArcadeState } from "@/types/arcade";

export interface Vec {
  x: number;
  y: number;
}

/** Player loadout, derived once from owned upgrade levels at run start. */
export interface Loadout {
  maxHealth: number; // 3 + max_health level
  canShoot: boolean; // Sidearm owned → auto-fire at the nearest enemy
  fireRateLevel: number; // 0..3 — shorter auto-fire interval
  slowMoLevel: number; // Overclock 0..3 — dodge slow-motion duration/cooldown
  scoreMult: number; // 1 + 0.25 × Combo Chip level
}

export type EnemyKind = "clock" | "hourglass" | "shard";

/**
 * The game's self-contained "arenas" — one per real app section. The game owns
 * this nav (it never touches the real router); the live app is a frozen backdrop.
 * Pomodoro is intentionally absent: it's a main-tab overlay, not a section.
 */
export type ArenaId = "calendar" | "queue" | "flashcard" | "settings" | "editor";

export interface Enemy {
  id: number;
  kind: EnemyKind;
  arena: ArenaId; // the sector this enemy lives in (only the active one is live)
  pos: Vec;
  vel: Vec;
  hp: number;
  maxHp: number;
  radius: number;
  emitTimer: number; // clock: seconds until the next spike ring
  flipTimer: number; // hourglass/shard: seconds until the next heading flip
  spin: number; // visual rotation (radians)
  spinRate: number;
  hitFlash: number; // brief flash after taking damage
  wanderTimer: number; // clock: seconds until it picks a new drift target
  wander: Vec;
}

/** Enemy projectile (the clock's radiating "spikes"). */
export interface Spike {
  id: number;
  pos: Vec;
  vel: Vec;
  radius: number;
  life: number;
}

/**
 * A bomb planted in an arena. Its fuse burns down everywhere (even while you're
 * in another sector — that's the threat); when it hits zero it hurts you. Shoot
 * or zap it in its arena to defuse before then. A bomb in a non-active arena
 * flashes that arena's nav button.
 */
export interface Bomb {
  id: number;
  arena: ArenaId;
  pos: Vec;
  hp: number;
  maxHp: number;
  fuse: number; // seconds remaining before it blows
  maxFuse: number;
  radius: number;
}

/** Player projectile (Sidearm bullets). */
export interface Bullet {
  id: number;
  pos: Vec;
  vel: Vec;
  life: number;
}

export interface Particle {
  pos: Vec;
  vel: Vec;
  life: number;
  maxLife: number;
  color: string;
  size: number;
}

/** A short-lived expanding ring drawn where the player clicked (the "zap"). */
export interface Zap {
  pos: Vec;
  life: number;
  maxLife: number;
  radius: number;
}

export interface FloatText {
  pos: Vec;
  vel: Vec;
  life: number;
  text: string;
  color: string;
}

export interface Player {
  pos: Vec;
  health: number;
  maxHealth: number;
  invuln: number; // i-frames remaining (seconds)
  zapCd: number; // click cooldown remaining
  hurt: number; // red-flash timer for HUD/screen feedback
}

export interface SlowMo {
  active: number; // remaining slow-motion seconds
  cooldown: number; // remaining cooldown before it can re-trigger
}

/** Per-arena skirmish bookkeeping (each sector progresses independently). */
export interface ArenaState {
  wave: number;
  pending: number; // enemies still to spawn this wave
  queue: EnemyKind[]; // spawn order for the current wave
  spawnTimer: number;
}

export interface World {
  w: number;
  h: number;
  load: Loadout;
  player: Player;
  slowmo: SlowMo;
  arena: ArenaId; // the active sector
  enemies: Enemy[]; // all sectors; only `arena`'s are live
  spikes: Spike[]; // active-sector projectiles (cleared on switch)
  bullets: Bullet[];
  bombs: Bomb[]; // all sectors; fuses burn everywhere
  particles: Particle[];
  zaps: Zap[];
  floats: FloatText[];
  arenas: Record<ArenaId, ArenaState>;
  bombTimer: number; // seconds until the next bomb is planted
  bannerArena: number; // seconds left to show the "ENTERING …" flash
  waveBanner: number; // seconds left to show the "WAVE N" flash
  score: number;
  status: "playing" | "over";
  shake: number; // screen-shake intensity, decays each frame
  nextId: number;
  elapsed: number;
}

export const COLORS = {
  cyan: "#6ffbff",
  pink: "#ff7bd5",
  yellow: "#ffe14d",
  green: "#74ff9c",
  bg: "#0a0617",
  grid: "rgba(120,90,200,0.10)",
} as const;

export interface ArenaDef {
  id: ArenaId;
  label: string;
  color: string; // theme accent (also tints the nav button)
}

/** Nav order, labels, and accent colors for the in-game sector switcher. */
export const ARENAS: ArenaDef[] = [
  { id: "calendar", label: "CALENDAR", color: COLORS.pink },
  { id: "queue", label: "QUEUE", color: COLORS.yellow },
  { id: "flashcard", label: "FLASHCARD", color: COLORS.green },
  { id: "settings", label: "SETTINGS", color: COLORS.cyan },
  { id: "editor", label: "EDITOR", color: "#b69cff" },
];

/**
 * Which enemy types spawn in each arena. Calendar → Clock and Queue → Hourglass
 * are the themed sectors; the other three reuse the Time-Pressure pool until
 * they get dedicated enemies. (`shard` only appears from a hourglass's death.)
 */
export const ARENA_POOL: Record<ArenaId, EnemyKind[]> = {
  calendar: ["clock"],
  queue: ["hourglass"],
  flashcard: ["clock", "hourglass"],
  settings: ["hourglass", "clock"],
  editor: ["clock", "hourglass"],
};

/** Per-frame input gathered by the React glue. */
export interface FrameInput {
  pointer: Vec; // absolute cursor position in world space
  clicked: boolean; // left button pressed this frame (manual zap)
  dodge: boolean; // dodge requested this frame (space / right-click)
}

/** Read the owned upgrade levels off the server state into a game loadout. */
export function loadoutFrom(state: ArcadeState | null): Loadout {
  const level = (key: string) =>
    state?.upgrades.find((u) => u.key === key)?.level ?? 0;
  return {
    maxHealth: 3 + level("max_health"),
    canShoot: level("shooting") >= 1,
    fireRateLevel: level("fire_rate"),
    slowMoLevel: level("move_speed"),
    scoreMult: 1 + 0.25 * level("score_multiplier"),
  };
}
