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

export interface Enemy {
  id: number;
  kind: EnemyKind;
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

export interface World {
  w: number;
  h: number;
  load: Loadout;
  player: Player;
  slowmo: SlowMo;
  enemies: Enemy[];
  spikes: Spike[];
  bullets: Bullet[];
  particles: Particle[];
  zaps: Zap[];
  floats: FloatText[];
  wave: number;
  pending: number; // enemies still to spawn this wave
  spawnTimer: number;
  waveBanner: number; // seconds left to show the "WAVE N" flash
  score: number;
  status: "playing" | "over";
  shake: number; // screen-shake intensity, decays each frame
  nextId: number;
  elapsed: number;
  _queue?: EnemyKind[]; // pending spawn order for the current wave
}

/** Per-frame input gathered by the React glue. */
export interface FrameInput {
  pointer: Vec; // absolute cursor position in world space
  clicked: boolean; // left button pressed this frame (manual zap)
  dodge: boolean; // dodge requested this frame (space / right-click)
}

export const COLORS = {
  cyan: "#6ffbff",
  pink: "#ff7bd5",
  yellow: "#ffe14d",
  green: "#74ff9c",
  bg: "#0a0617",
  grid: "rgba(120,90,200,0.10)",
} as const;

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
