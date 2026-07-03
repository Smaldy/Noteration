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

/**
 * Player loadout, derived once from owned skill levels at run start. Each field
 * maps to one skill key (see `loadoutFrom`); the sim reads these, never the raw
 * upgrade rows, so adding a skill is: add a field here + read it in `world.ts`.
 */
export interface Loadout {
  maxHealth: number; // 3 + max_health level
  zapDamage: number; // click-burst (area) damage — base 1 + zap_damage level
  zapReach: number; // click-burst radius in px — base + zap_reach level
  canShoot: boolean; // Sidearm owned → click fires a bullet burst
  fireRateLevel: number; // Rapid Fire — more bullets per click-burst
  autoFireLevel: number; // Auto-Turret 0..10 — 0 = off; higher = faster auto-fire
  slowMoLevel: number; // Overclock 0..10 — dodge slow-motion duration/cooldown
  scoreMult: number; // 1 + 0.25 × Combo Chip level
  defuseSpeedLevel: number; // Quick Hands — shorter hold-to-defuse
  defuseWindowLevel: number; // Long Fuse — longer bomb fuses
  defuseFreezeLevel: number; // Dampening Field — slows a fuse while defusing it
  phaseShieldLevel: number; // Phase Cloak 0..10 — periodic ignore-damage window
  pusherCdLevel: number; // Defuser Pusher 0..10 — shorter shockwave cooldown (60s→20s)
  bulletDamageLevel: number; // Hollow Points — +1 bullet damage per level
  bulletSpeedLevel: number; // Railgun — faster, longer-range bullets
  recallLevel: number; // Recall Beacon — shorter right-click hold to warp home
  prestige: number; // prestige count — +20% to every attack's damage each
  special: "none" | "electric" | "love"; // active tier-6 special bullet
}

export type EnemyKind =
  | "hunter"
  | "shooter"
  | "clock"
  | "hourglass"
  | "shard"
  | "dasher"
  | "beamer";

/**
 * The game's "arenas" — one per real app page. The active sector is derived from
 * the real route: the player navigates with the app's *own* buttons (the Library
 * header buttons, and each page's "← Library" return button), which change the
 * page and the sector together. Calendar and Queue are the themed sectors;
 * Pomodoro is intentionally absent (it's a main-tab overlay, not a page).
 */
export type ArenaId = "library" | "exam" | "calendar" | "queue" | "settings";

export interface Enemy {
  id: number;
  kind: EnemyKind;
  arena: ArenaId; // the sector this enemy lives in (only the active one is live)
  pos: Vec;
  vel: Vec;
  hp: number;
  maxHp: number;
  radius: number;
  speed: number; // movement speed
  contactDmg: number; // hearts lost when it touches the cursor
  reload: number; // seconds until its next ability use (clock ring / shooter bolt)
  reloadTime: number; // base cooldown between ability uses
  isBoss: boolean; // a 10-wave boss: bigger, tankier, hits harder
  flipTimer: number; // hourglass/shard: seconds until the next heading flip
  spin: number; // visual rotation (radians)
  spinRate: number;
  hitFlash: number; // brief flash after taking damage
  wanderTimer: number; // clock: seconds until it picks a new drift target
  wander: Vec;
  // Telegraphed-attack state (dasher lunge / beamer laser; reused by bosses).
  windup: number; // >0 while charging an attack (the telegraph)
  aimAngle: number; // locked firing/dash direction (radians)
  armed: boolean; // telegraph has LOCKED its aim (final pre-fire window — evadeable)
  dashTime: number; // dasher: remaining seconds of an active dash
  dashCd: number; // boss-only: seconds until the next signature dash
  flips: number; // hourglass/shard: heading-flips so far (dashes once it hits the threshold)
  flipAnim: number; // hourglass/shard: seconds left in the current flip animation
  // Clock-boss illusion state.
  isClone: boolean; // a damage-less decoy of the clock boss (doesn't fire/hurt)
  cloneCd: number; // clock boss: seconds until the next teleport + clone cycle
  // Love-bullet charm: turned to your side, fights the swarm for a while.
  charmed: boolean;
  charmTimer: number; // seconds of charm left before it poofs
}

/**
 * Enemy projectile. A plain bolt (the shooter's) renders as a small diamond.
 * The clock's thrown clock-hands set `len`/`spin`/`color` and render as spinning
 * rods. `dmg` lets a boss's projectile cost more than one heart.
 */
export interface Spike {
  id: number;
  pos: Vec;
  vel: Vec;
  radius: number;
  life: number;
  dmg?: number; // hearts on hit (default 1)
  len?: number; // set → render as a clock-hand rod of this length (px)
  spin?: number; // current rod rotation (radians); advanced each frame
  spinRate?: number; // rod tumble speed
  color?: string; // rod color (the clock's accent)
}

/**
 * A bomb planted in an arena. Its fuse burns down everywhere (even while you're
 * in another sector — that's the threat); when it hits zero it costs a heart. To
 * defuse, stand on it in its sector and *hold* the click until the defuse meter
 * fills (`defuseTime` seconds). A bomb in a non-active sector glows its nav button.
 */
export interface Bomb {
  id: number;
  arena: ArenaId;
  pos: Vec;
  fuse: number; // seconds remaining before it blows
  maxFuse: number;
  defuse: number; // hold-to-defuse progress, 0..1
  defuseTime: number; // seconds of holding needed to fully defuse
  radius: number;
  defusing: boolean; // set each frame while actively being defused (Dampening Field)
}

/**
 * A laser beam fired by a beamer (or, amplified, a beamer boss). A straight
 * damaging segment from `pos` along `angle` for `len` px, alive briefly after a
 * telegraphed wind-up. Hits the player (i-frames gate repeat damage); cosmetic
 * to enemies.
 */
export interface Beam {
  id: number;
  pos: Vec; // origin (the firer's position when it fired)
  angle: number;
  len: number;
  life: number;
  maxLife: number;
  width: number;
  dmg: number;
}

/**
 * A floor pickup. Bosses drop a `health` pack on death; walk the cursor over it
 * (in its sector) to collect. `kind` is open for future drop types.
 */
export interface Pickup {
  id: number;
  arena: ArenaId; // the sector it was dropped in (only collectable there)
  kind: "health";
  pos: Vec;
  value: number; // hearts restored
  life: number; // seconds before it fades away
  maxLife: number;
  bob: number; // animation phase
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
  cooldownMax: number; // the full cooldown of the last trigger (for the HUD ring)
}

/** Phase Cloak: a recurring auto-invuln window. `active` ticks down while the
 *  cloak is up; `cooldown` ticks down between windows (interval shrinks 30s→20s
 *  as the skill is leveled). Inert unless `load.phaseShieldLevel > 0`. */
export interface PhaseShield {
  active: number;
  cooldown: number;
  interval: number; // the full between-window interval (for the HUD ring)
}

/** Defuser Pusher: a built-in ability. Defusing a bomb releases a non-damaging
 *  shockwave that shoves every enemy in the sector away — but only once its
 *  cooldown has recharged. `cooldown` ticks down to 0 (ready); `interval` is the
 *  full recharge time (for the HUD ring). */
export interface Pusher {
  cooldown: number;
  interval: number;
}

/** Per-arena spawn bookkeeping. The wave number itself is global (one shared
 *  level across all sectors), only the in-flight spawn batch is per-sector. */
export interface ArenaState {
  pending: number; // enemies still to spawn this wave
  queue: EnemyKind[]; // spawn order for the current wave
  spawnTimer: number;
  total: number; // enemies in this wave (spawned + pending) — for the HUD counter
}

export interface World {
  w: number;
  h: number;
  load: Loadout;
  player: Player;
  slowmo: SlowMo;
  phase: PhaseShield; // Phase Cloak timers
  pusher: Pusher; // Defuser Pusher: defuse-shockwave cooldown
  autoFireCd: number; // Auto-Turret: seconds until the next auto-shot
  arena: ArenaId; // the active sector
  enemies: Enemy[]; // all sectors; only `arena`'s are live
  spikes: Spike[]; // active-sector projectiles (cleared on switch)
  beams: Beam[]; // active-sector laser beams (beamer / beamer boss)
  pickups: Pickup[]; // dropped items (boss health packs); persist across sectors
  bullets: Bullet[];
  bombs: Bomb[]; // all sectors; fuses burn everywhere
  particles: Particle[];
  zaps: Zap[];
  floats: FloatText[];
  arenas: Record<ArenaId, ArenaState>;
  wave: number; // global wave level, shared across all sectors
  bombTimer: number; // seconds until the next bomb is planted
  bombStreak: number; // consecutive bombs that blew up (escalates detonation dmg)
  bannerArena: number; // seconds left to show the "ENTERING …" flash
  bossBanner: number; // seconds left to show the "A NEW BOSS SPAWNED" scare
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

/** Accent color per enemy kind (drawing + death particles/score text). */
export const ENEMY_COLOR: Record<EnemyKind, string> = {
  hunter: "#ff6a8a",
  shooter: COLORS.cyan,
  clock: COLORS.pink,
  hourglass: COLORS.yellow,
  shard: COLORS.green,
  dasher: "#ff9f43", // orange — the lunging stalker
  beamer: "#b388ff", // violet — the laser sentinel
};

export interface ArenaDef {
  id: ArenaId;
  label: string; // uppercase label for the in-canvas sector banner
  route: string; // the real app route this sector maps to
  color: string; // theme accent (canvas banner + HUD label)
}

/**
 * Every sector and the real route it maps to (`/` is the Library hub). Order is
 * the **unlock order**: library is always open, each later sector unlocks every
 * 5 waves (calendar@5, queue@10, exam@15, settings@20).
 */
export const ARENAS: ArenaDef[] = [
  { id: "library", label: "LIBRARY", route: "/", color: COLORS.green },
  { id: "calendar", label: "CALENDAR", route: "/calendar", color: COLORS.pink },
  { id: "queue", label: "QUEUE", route: "/queue", color: COLORS.yellow },
  { id: "exam", label: "EXAM PREP", route: "/exam", color: COLORS.cyan },
  { id: "settings", label: "SETTINGS", route: "/settings", color: "#b69cff" },
];

/** Map a real route to its sector (longest non-root prefix wins; `/` → library). */
export function arenaForPath(path: string): ArenaId {
  const hit = ARENAS.find((a) => a.route !== "/" && path.startsWith(a.route));
  return hit?.id ?? "library";
}

/** A sector is open once the global wave reaches its unlock threshold. */
export function sectorUnlocked(id: ArenaId, wave: number): boolean {
  return ARENAS.findIndex((a) => a.id === id) * 5 <= wave;
}

/** The sectors currently unlocked at a given wave. */
export function unlockedSectorIds(wave: number): ArenaId[] {
  return ARENAS.filter((a) => sectorUnlocked(a.id, wave)).map((a) => a.id);
}

/**
 * Which enemy types spawn in each sector. Library (always open) breeds the plain
 * cursor-hunting **hunter**; each unlocked sector adds its own special:
 * Calendar → Clock (spike rings), Queue → Hourglass (splitter), Exam → Beamer
 * (charged laser), Settings → a Beamer/Dasher/Clock mix. Each sector's first
 * entry is its boss kind. (`shard` only appears from a hourglass's death.)
 */
export const ARENA_POOL: Record<ArenaId, EnemyKind[]> = {
  library: ["hunter"],
  calendar: ["clock", "hunter"],
  queue: ["hourglass", "hunter"],
  exam: ["beamer", "shooter"], // Exam Prep — laser sentinels (boss = beamer)
  settings: ["beamer", "dasher", "clock"],
};

/** Per-frame input gathered by the React glue. */
export interface FrameInput {
  pointer: Vec; // absolute cursor position in world space
  clicked: boolean; // left button pressed this frame (edge — fires the zap/shot)
  held: boolean; // left button currently down (level — drives hold-to-defuse)
  dodge: boolean; // dodge requested this frame (space / right-click)
}

/** Read the owned upgrade levels off the server state into a game loadout. */
export function loadoutFrom(state: ArcadeState | null): Loadout {
  const level = (key: string) =>
    state?.upgrades.find((u) => u.key === key)?.level ?? 0;
  // Prestige grants +20% to every attack's damage, applied to the owned levels.
  const prestige = state?.prestige_count ?? 0;
  const dmgMult = 1 + 0.2 * prestige;
  const special = (state?.active_special ?? "none") as Loadout["special"];
  return {
    maxHealth: 3 + level("max_health"),
    zapDamage: (1 + level("zap_damage")) * dmgMult,
    zapReach: 64 + 12 * level("zap_reach"),
    canShoot: level("shooting") >= 1,
    fireRateLevel: level("fire_rate"),
    autoFireLevel: level("auto_fire"),
    slowMoLevel: level("move_speed"),
    scoreMult: 1 + 0.25 * level("score_multiplier"),
    defuseSpeedLevel: level("defuse_speed"),
    defuseWindowLevel: level("defuse_window"),
    defuseFreezeLevel: level("defuse_freeze"),
    phaseShieldLevel: level("phase_shield"),
    pusherCdLevel: level("pusher_cd"),
    bulletDamageLevel: level("bullet_damage"),
    bulletSpeedLevel: level("bullet_speed"),
    recallLevel: level("recall"),
    prestige,
    special: special === "electric" || special === "love" ? special : "none",
  };
}
