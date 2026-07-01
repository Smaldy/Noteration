/**
 * NOTINVASION — the simulation. `createWorld` builds the starting state; `step`
 * advances it by one frame given the player's input. Everything is plain math on
 * the `World` struct (no React, no canvas) so the rules are deterministic and
 * testable. Rendering lives in `render.ts`.
 *
 * The game plays over the frozen Noteration app across self-contained "arenas"
 * (one per section). Enemies are themed to their sector — Clocks in the Calendar,
 * Hourglasses in the Queue — and each sector is its own persistent skirmish:
 * enemies freeze while you're away. Bombs can be planted in any sector and their
 * fuses burn everywhere, so a bomb in another sector forces you to switch to it
 * (its nav button flashes) and shoot it down before it blows.
 *
 *   · Clock     — drifts, periodically radiates a ring of spikes; click the face.
 *   · Hourglass — slow, flips heading unpredictably, splits into two shards on death.
 *   · Shard     — a fast half-hourglass spawned on a hourglass's death.
 */
import {
  ARENA_POOL,
  ARENAS,
  type ArenaId,
  type ArenaState,
  type Beam,
  type Bomb,
  COLORS,
  type Enemy,
  ENEMY_COLOR,
  type EnemyKind,
  type FrameInput,
  type Loadout,
  unlockedSectorIds,
  type Vec,
  type World,
} from "./types";

// ── Tunables ────────────────────────────────────────────────────────────────
const PLAYER_R = 9;
const ZAP_CD = 0.22; // min seconds between click-bursts
const INVULN = 1.15;
const BULLET_SPEED = 560; // base; Railgun (bulletSpeedLevel) adds to this
const BULLET_R = 5;

// Special bullets (tier 6, prestige-unlocked). Electric chains a share of its
// damage to nearby enemies; Love tries to charm the enemy it hits (harder the
// more health it has) into fighting the swarm for you.
const ELECTRIC_RADIUS = 120; // chain reach (px)
const ELECTRIC_SHARE = 0.55; // fraction of the hit's damage dealt to neighbors
const CHARM_BASE = 1.4; // charm chance = min(0.9, CHARM_BASE / enemy hp)
const CHARM_DURATION = 14; // seconds a charmed enemy fights before it poofs
const LOVE_COLOR = "#ff7bd5";
const ELECTRIC_COLOR = "#8ad8ff";
const SPIKE_R = 6;
const SLOW_FACTOR = 0.32; // enemy/spike time multiplier during Overclock

const BOMB_R = 22;
const BOMB_FUSE = 12; // seconds before a planted bomb blows
const MAX_BOMBS = 2;
const BOMB_POINTS = 50;

// Spawn pacing & difficulty. Early waves throw a LARGER batch of enemies but
// trickle them in slowly; later waves spawn faster. A hard cap on simultaneous
// live enemies keeps the frame budget (and the lag) in check. Difficulty steps
// up every 10 waves (the `tier`): enemies hit harder, spawn faster, bombs sooner.
const MAX_ACTIVE_ENEMIES = 16; // most enemies live in a sector at once (anti-lag)
const ENEMY_DMG_TIER_CAP = 2; // most extra contact damage from wave tiers

/** Difficulty tier — one step every 10 waves. */
function waveTier(wave: number): number {
  return Math.floor(wave / 10);
}

/** Enemies queued for a (non-boss) wave: a big early batch that still grows. */
function waveCount(wave: number): number {
  return 4 + Math.floor(wave * 0.7);
}

/** Seconds between spawns: slow early (so a big batch trickles in), faster as
 *  the run climbs and at each 10-wave tier. */
function spawnInterval(wave: number): number {
  return Math.max(0.3, 0.85 - wave * 0.02 - waveTier(wave) * 0.05);
}

/** Seconds until the next bomb is planted: long early, shrinking with waves and
 *  tiers, plus a random jitter so it's never on a predictable beat. */
function bombInterval(wave: number): number {
  const base = Math.max(7, 20 - wave * 0.4 - waveTier(wave) * 1.5);
  return base + Math.random() * 6;
}
const DEFUSE_MIN = 2; // hold-to-defuse seconds (randomized per bomb)
const DEFUSE_MAX = 5;
const DEFUSE_REACH = 30; // how close the cursor must be to hold-defuse a bomb
const DEFUSE_DECAY = 0.6; // progress lost per second when not holding on it

const PLAYER_KNOCKBACK = 20; // how far an enemy is shoved off after touching you
const BOLT_SPEED = 240; // shooter projectile speed

// Dasher lunge. Winds up (telegraph), then streaks at the cursor at DASH_MULT×
// its base speed for DASH_TIME seconds. Bosses amplify all three.
const DASH_WINDUP = 0.5;
const DASH_TIME = 0.3;
const DASH_MULT = 5.5;

// Beamer laser. Charges (telegraph) while tracking the cursor, then LOCKS the
// aim for a final window before it fires — so the beam is dodgeable instead of a
// guaranteed hit. The shot goes off along the locked angle, not the live cursor.
// Bosses charge faster and fire a fan (but still telegraph + lock).
const BEAM_WINDUP = 1.15; // total charge time (was 0.85; longer = more warning)
const BEAM_LOCK = 0.55; // final seconds with the aim FROZEN (the evade window)
const BEAM_LIFE = 0.16;
const BEAM_LEN = 1400;
const BEAM_WIDTH = 11;

// Hourglass / shard dash. They harmlessly drift and flip heading; once they've
// flipped enough times they turn aggressive and lunge at the cursor (telegraphed,
// so it's evadeable), then pause and do it again. Shards charge sooner & faster.
const HG_FLIPS_TO_DASH = 2; // hourglass dashes after this many flips
const HG_DASH_WINDUP = 0.45; // telegraph before an hourglass lunge
const HG_DASH_TIME = 0.6; // seconds of an active hourglass lunge (longer reach)
const HG_DASH_MULT = 16; // lunge speed = base speed × this (far-reaching now)
const HG_DASH_CD = 1.3; // pause between hourglass lunges
const SHARD_FLIPS_TO_DASH = 1; // the mini ones turn aggressive sooner
const SHARD_DASH_WINDUP = 0.3; // …and telegraph faster
const SHARD_DASH_MULT = 14; // …and lunge faster/farther

// Defuser Pusher (built-in ability): defusing a bomb releases a non-damaging
// shockwave that shoves every enemy in the sector outward. Recharge starts at
// 60s and the Defuser Pusher skill shortens it toward 20s at level 10.
const PUSHER_CD = 60; // recharge seconds at level 0
const PUSHER_CD_MIN = 20; // recharge at level 10
const PUSHER_RADIUS = 280; // visual blast radius
const PUSHER_SHOVE = 230; // px each enemy is pushed
const PUSHER_IMPULSE = 320; // extra outward velocity imparted

/** Defuser Pusher recharge (seconds) at a given skill level (60s → 20s). */
function pusherInterval(level: number): number {
  return Math.max(PUSHER_CD_MIN, PUSHER_CD - (PUSHER_CD - PUSHER_CD_MIN) * (level / 10));
}

/** Bullet damage from owned levels (Hollow Points) × prestige bonus. */
function bulletDamage(load: Loadout): number {
  return (1 + load.bulletDamageLevel) * (1 + 0.2 * load.prestige);
}

/** Bullet muzzle speed from Railgun level. */
function bulletSpeed(load: Loadout): number {
  return BULLET_SPEED + 90 * load.bulletSpeedLevel;
}

/** Bullet lifetime (→ range) scaled by Railgun level. */
function bulletLife(load: Loadout, base: number): number {
  return base * (1 + 0.12 * load.bulletSpeedLevel);
}

// Every boss gains a signature dash (the "much more powerful ability"): bosses
// of kinds that have no dash/beam of their own periodically telegraph and lunge
// across the arena at the cursor, on top of their normal attacks. Bosses cover a
// LOT more ground than a regular dasher (longer + faster lunge).
const BOSS_DASH_CD = 3.0;
const BOSS_DASH_WINDUP = 0.4;
const BOSS_DASH_TIME = 0.5; // longer lunge…
const BOSS_DASH_MULT = 15; // …and WAY faster ⇒ it crosses the arena in a blink

// Boss health is a big multiple of a regular enemy's (a real damage sponge).
const BOSS_HP_MULT = 60;

// Failing to defuse a bomb (letting it blow) builds a streak that escalates the
// detonation damage from 1 heart up to MAX; defusing any bomb resets the streak.
const BOMB_FAIL_DMG_MAX = 4;

// Clock boss — the teleporting illusionist. Two signature abilities on top of
// the hand-projectiles every clock now throws (see fireHands):
//   1. Each cycle it TELEPORTS (sometimes right next to you) and conjures
//      damage-less CLONES of itself, each with a fake healthbar, so you lose the
//      real one. The tell: only the REAL boss keeps firing its hands.
//   2. Its hands regrow after being thrown (the regular clocks' too).
const CLOCK_HAND_SPEED = 300; // thrown-hand projectile speed
const CLOCK_CLONE_CD = 4.6; // seconds between teleport + clone cycles
const CLOCK_CLONE_COUNT = 3; // decoys conjured each cycle
const CLOCK_TP_NEAR_CHANCE = 0.5; // chance the real boss blinks next to the player
const CLOCK_TP_NEAR_DIST = 150; // how close "next to the player" lands

// Hourglass flip — a literal flip (squash to edge-on and reopen), not a spin.
const HG_FLIP_DUR = 0.34;

// Health pack dropped on a boss kill.
const PICKUP_R = 17;
const PICKUP_LIFE = 16;
const HEALTH_PACK_VALUE = 2;

// Auto-Turret (auto_fire): fires an aimed bullet at the nearest enemy on a timer
// that shortens with level. Independent of the Sidearm (the manual click-burst).
const AUTO_FIRE_BASE = 0.85; // interval (s) at level 1
const AUTO_FIRE_STEP = 0.06; // faster per level
const AUTO_FIRE_MIN = 0.14; // floor on the interval

// Phase Cloak (phase_shield): a recurring auto-invuln window. The interval
// shrinks linearly from 30s (level 1) to 20s (level PHASE_MAX_LEVEL).
const PHASE_DUR = 2.5; // seconds of ignore-damage per window
const PHASE_CD_HI = 30; // interval at level 1
const PHASE_CD_LO = 20; // interval at max level
const PHASE_MAX_LEVEL = 10;

// Bomb-defuse skills.
const DEFUSE_WINDOW_STEP = 1.0; // Long Fuse: +1s of fuse per level
const DEFUSE_SPEED_STEP = 0.07; // Quick Hands: -7% hold time per level
const DEFUSE_TIME_MIN = 0.6; // floor on the hold-to-defuse time
const DEFUSE_FREEZE_STEP = 0.08; // Dampening Field: -8% fuse burn while defusing
const DEFUSE_BURN_MIN = 0.1; // a defused fuse never fully freezes

/** Phase Cloak interval (seconds) at a given level; Infinity when unowned. */
function phaseInterval(level: number): number {
  if (level <= 0) return Infinity;
  const t = Math.min(1, (level - 1) / (PHASE_MAX_LEVEL - 1));
  return PHASE_CD_HI - (PHASE_CD_HI - PHASE_CD_LO) * t;
}

// hp/radius/speed, ability cooldown (`reload`, 999 = no ability — melee only),
// contact damage, and score. Bosses scale these up at spawn.
const ENEMY: Record<
  EnemyKind,
  { hp: number; r: number; speed: number; reload: number; contact: number; points: number }
> = {
  hunter: { hp: 2, r: 16, speed: 92, reload: 999, contact: 1, points: 12 },
  shooter: { hp: 2, r: 18, speed: 48, reload: 1.9, contact: 1, points: 20 },
  clock: { hp: 3, r: 26, speed: 30, reload: 2.4, contact: 1, points: 26 },
  hourglass: { hp: 2, r: 22, speed: 26, reload: 999, contact: 1, points: 16 },
  shard: { hp: 1, r: 13, speed: 88, reload: 999, contact: 1, points: 7 },
  // Dasher: drifts slow, then telegraphs and lunges fast at the cursor (`reload`
  // is the cooldown between lunges). Beamer: holds range and fires a charged laser.
  dasher: { hp: 2, r: 15, speed: 64, reload: 2.6, contact: 1, points: 18 },
  beamer: { hp: 3, r: 20, speed: 34, reload: 3.2, contact: 1, points: 24 },
};

// ── Construction ─────────────────────────────────────────────────────────────
export function createWorld(
  w: number,
  h: number,
  load: Loadout,
  startWave: number,
  startScore: number,
): World {
  const wave = Math.max(1, startWave);
  const arenas = {} as Record<ArenaId, ArenaState>;
  for (const a of ARENAS) arenas[a.id] = { pending: 0, queue: [], spawnTimer: 0, total: 0 };

  const world: World = {
    w,
    h,
    load,
    player: {
      pos: { x: w / 2, y: h / 2 },
      health: load.maxHealth,
      maxHealth: load.maxHealth,
      invuln: 1.5, // brief grace at run start
      zapCd: 0,
      hurt: 0,
    },
    slowmo: { active: 0, cooldown: 0, cooldownMax: Math.max(2.5, 6 - load.slowMoLevel) },
    phase: {
      active: 0,
      cooldown: phaseInterval(load.phaseShieldLevel),
      interval: phaseInterval(load.phaseShieldLevel),
    },
    // Ready from the first defuse; Defuser Pusher skill shortens the recharge.
    pusher: { cooldown: 0, interval: pusherInterval(load.pusherCdLevel) },
    autoFireCd: 0,
    arena: "library", // synced to the real route on mount
    enemies: [],
    spikes: [],
    beams: [],
    pickups: [],
    bullets: [],
    bombs: [],
    particles: [],
    zaps: [],
    floats: [],
    arenas,
    wave,
    bombTimer: bombInterval(wave),
    bombStreak: 0,
    bannerArena: 1.4,
    bossBanner: 0,
    waveBanner: 1.4,
    score: Math.max(0, startScore),
    status: "playing",
    shake: 0,
    nextId: 1,
    elapsed: 0,
  };
  for (const a of ARENAS) setupWave(world, a.id);
  return world;
}

function setupWave(world: World, arena: ArenaId, boss = false) {
  const st = world.arenas[arena];
  const pool = ARENA_POOL[arena];
  if (boss && arena === world.arena) {
    // Boss wave: the sector's headline enemy, beefed, plus a few minions. The
    // boss is a duel — clear every planted bomb so nothing forces you to leave
    // (and `stepBombs` won't plant new ones while the boss lives).
    world.bombs = [];
    spawnEnemy(world, pool[0], arena, { boss: true });
    world.bossBanner = 3.6;
    const minions = 3;
    st.queue = Array.from({ length: minions }, (_, i) => pool[i % pool.length]);
  } else {
    const count = waveCount(world.wave);
    st.queue = Array.from({ length: count }, (_, i) => pool[i % pool.length]);
  }
  st.pending = st.queue.length;
  // The boss itself is already spawned (not in the queue), so count it too.
  st.total = st.queue.length + (boss && arena === world.arena ? 1 : 0);
  st.spawnTimer = 0.4;
  if (arena === world.arena && !boss) world.waveBanner = 1.4; // boss banner shows instead
}

/** Switch the active sector. Enemies persist (frozen); transient spikes reset.
 *  A previously-cleared sector is re-armed on entry at the current global wave
 *  (without advancing it — only clearing a sector you're fighting advances it). */
export function switchArena(world: World, arena: ArenaId) {
  if (arena === world.arena || world.status !== "playing") return;
  // A boss is a duel: you can't leave its sector until it's dead.
  if (bossActive(world) && arena !== world.arena) return;
  world.arena = arena;
  world.spikes = [];
  world.beams = [];
  world.bannerArena = 1.3;
  world.player.invuln = Math.max(world.player.invuln, 0.8); // grace on arrival
  const st = world.arenas[arena];
  if (st.pending === 0 && !world.enemies.some((e) => e.arena === arena)) {
    setupWave(world, arena);
  }
}

// ── Helpers ──────────────────────────────────────────────────────────────────
const dist2 = (a: Vec, b: Vec) => {
  const dx = a.x - b.x;
  const dy = a.y - b.y;
  return dx * dx + dy * dy;
};
const clamp = (v: number, lo: number, hi: number) => (v < lo ? lo : v > hi ? hi : v);

function edgePoint(world: World): Vec {
  // Spawn just outside a random edge so enemies slide into the arena.
  const m = 36;
  switch (Math.floor(Math.random() * 4)) {
    case 0:
      return { x: Math.random() * world.w, y: -m };
    case 1:
      return { x: Math.random() * world.w, y: world.h + m };
    case 2:
      return { x: -m, y: Math.random() * world.h };
    default:
      return { x: world.w + m, y: Math.random() * world.h };
  }
}

function spawnEnemy(
  world: World,
  kind: EnemyKind,
  arena: ArenaId,
  opts: { at?: Vec; boss?: boolean; clone?: boolean } = {},
) {
  const base = ENEMY[kind];
  const clone = opts.clone ?? false;
  const boss = (opts.boss ?? false) || clone; // a clone wears the boss's body
  const pos = opts.at ?? edgePoint(world);
  const ang = Math.random() * Math.PI * 2;
  const waveScale = 1 + (world.wave - 1) * 0.05;
  const hp = Math.max(1, Math.round(base.hp * waveScale)) * (boss ? BOSS_HP_MULT : 1);
  const speed = base.speed * (boss ? 0.85 : 1);
  const reloadTime = base.reload * (boss ? 0.55 : 1);
  // Damage upgrade every 10 waves: regular enemies gain up to +2 contact damage
  // with the wave tier. A boss always hits for DOUBLE a regular enemy of the same
  // tier — so it stays the scariest thing on screen no matter the wave.
  const tierDmg = Math.min(ENEMY_DMG_TIER_CAP, waveTier(world.wave));
  const regularDmg = base.contact + tierDmg;
  const contactDmg = boss ? regularDmg * 2 : regularDmg;
  world.enemies.push({
    id: world.nextId++,
    kind,
    arena,
    pos,
    vel: { x: Math.cos(ang) * speed, y: Math.sin(ang) * speed },
    // A clone shows a fake, partial healthbar (so it doesn't read as obviously
    // full) — but it's invulnerable, so the bar never actually moves.
    hp: clone ? Math.max(1, Math.round(hp * (0.3 + Math.random() * 0.7))) : hp,
    maxHp: hp,
    radius: base.r * (boss ? 1.9 : 1),
    speed,
    contactDmg: clone ? 0 : contactDmg, // illusions never hurt
    reload: 1 + Math.random() * Math.min(reloadTime, 2),
    reloadTime,
    isBoss: boss,
    flipTimer: 1 + Math.random() * 1.5,
    spin: Math.random() * Math.PI * 2,
    spinRate: (Math.random() < 0.5 ? -1 : 1) * (0.4 + Math.random()),
    hitFlash: 0,
    wanderTimer: 0,
    wander: { x: world.w / 2, y: world.h / 2 },
    windup: 0,
    aimAngle: 0,
    armed: false,
    dashTime: 0,
    dashCd: BOSS_DASH_CD * (0.6 + Math.random() * 0.5),
    flips: 0,
    flipAnim: 0,
    isClone: clone,
    cloneCd: CLOCK_CLONE_CD * (0.7 + Math.random() * 0.4),
    charmed: false,
    charmTimer: 0,
  });
}

function burst(world: World, pos: Vec, color: string, n: number) {
  for (let i = 0; i < n; i++) {
    const a = Math.random() * Math.PI * 2;
    const s = 60 + Math.random() * 200;
    world.particles.push({
      pos: { ...pos },
      vel: { x: Math.cos(a) * s, y: Math.sin(a) * s },
      life: 0.4 + Math.random() * 0.4,
      maxLife: 0.8,
      color,
      size: 2 + Math.random() * 2,
    });
  }
}

function floatText(world: World, pos: Vec, text: string, color: string) {
  world.floats.push({ pos: { ...pos }, vel: { x: 0, y: -38 }, life: 0.9, text, color });
}

// ── Step ─────────────────────────────────────────────────────────────────────
export function step(world: World, dtRaw: number, input: FrameInput): void {
  if (world.status !== "playing") return;
  const dt = clamp(dtRaw, 0, 0.05); // guard against tab-stall spirals
  world.elapsed += dt;

  // Slow-motion (Overclock) only scales the enemy/projectile clock.
  if (input.dodge && world.slowmo.cooldown <= 0 && world.load.slowMoLevel > 0) {
    world.slowmo.active = 0.55 + 0.2 * world.load.slowMoLevel;
    world.slowmo.cooldown = Math.max(2.5, 6 - world.load.slowMoLevel);
    world.slowmo.cooldownMax = world.slowmo.cooldown;
  }
  world.slowmo.active = Math.max(0, world.slowmo.active - dt);
  world.slowmo.cooldown = Math.max(0, world.slowmo.cooldown - dt);
  const edt = world.slowmo.active > 0 ? dt * SLOW_FACTOR : dt;

  // Phase Cloak: on its own clock, periodically grant a brief ignore-damage
  // window (keeps player i-frames topped up while it's up).
  if (world.load.phaseShieldLevel > 0) {
    if (world.phase.active > 0) {
      world.phase.active = Math.max(0, world.phase.active - dt);
    } else {
      world.phase.cooldown -= dt;
      if (world.phase.cooldown <= 0) {
        world.phase.active = PHASE_DUR;
        world.phase.cooldown = phaseInterval(world.load.phaseShieldLevel);
      }
    }
    if (world.phase.active > 0) {
      world.player.invuln = Math.max(world.player.invuln, world.phase.active);
    }
  }

  // Defuser Pusher recharge (the shockwave itself fires from `defuseBomb`).
  world.pusher.cooldown = Math.max(0, world.pusher.cooldown - dt);

  stepPlayer(world, dt, input);
  stepWave(world, dt);
  stepEnemies(world, edt);
  stepSpikes(world, edt);
  stepBeams(world, edt);
  stepBullets(world, dt);
  stepBombs(world, dt);
  stepPickups(world, dt);
  stepEffects(world, dt);

  world.bannerArena = Math.max(0, world.bannerArena - dt);
  world.bossBanner = Math.max(0, world.bossBanner - dt);
  world.shake = Math.max(0, world.shake - dt * 60);
  if (world.player.health <= 0) world.status = "over";
}

function stepPlayer(world: World, dt: number, input: FrameInput) {
  const p = world.player;
  p.pos.x = clamp(input.pointer.x, 0, world.w);
  p.pos.y = clamp(input.pointer.y, 0, world.h);
  p.invuln = Math.max(0, p.invuln - dt);
  p.hurt = Math.max(0, p.hurt - dt);
  p.zapCd = Math.max(0, p.zapCd - dt);

  // Click attack: a short-range area zap (always) plus — once the Sidearm is
  // owned — a radiating burst of bullets. Shockwave scales the zap's damage and
  // Resonance Field its radius (`load.zapReach`).
  if (input.clicked && p.zapCd <= 0) {
    p.zapCd = ZAP_CD;
    const reach = world.load.zapReach;
    world.zaps.push({ pos: { ...p.pos }, life: 0.26, maxLife: 0.26, radius: reach });
    const r2 = reach * reach;
    for (const e of world.enemies) {
      // Decoys and charmed allies are untouchable by your own fire.
      if (e.arena !== world.arena || e.isClone || e.charmed) continue;
      if (dist2(e.pos, p.pos) <= r2 + e.radius * e.radius)
        damageEnemy(world, e, world.load.zapDamage);
    }
    if (world.load.canShoot) fireBurst(world);
  }

  // Auto-Turret: on its own timer, fire an aimed bullet at the nearest enemy.
  if (world.load.autoFireLevel > 0) {
    world.autoFireCd -= dt;
    if (world.autoFireCd <= 0) {
      world.autoFireCd = Math.max(
        AUTO_FIRE_MIN,
        AUTO_FIRE_BASE - AUTO_FIRE_STEP * (world.load.autoFireLevel - 1),
      );
      autoFire(world);
    }
  }

  // Hold the click on a bomb in this sector to defuse it: the meter fills over
  // `defuseTime`, and bleeds back down when you step off it. `defusing` is
  // republished each frame so Dampening Field can slow the fuse in `stepBombs`.
  for (const b of world.bombs) {
    b.defusing = false;
    if (b.arena !== world.arena) continue;
    const reach = b.radius + DEFUSE_REACH;
    const onIt = dist2(b.pos, p.pos) <= reach * reach;
    if (input.held && onIt) {
      b.defusing = true;
      b.defuse += dt / b.defuseTime;
      if (b.defuse >= 1) defuseBomb(world, b);
    } else if (b.defuse > 0) {
      b.defuse = Math.max(0, b.defuse - dt * DEFUSE_DECAY);
    }
  }
}

/** Auto-Turret shot: aim a single bullet at the nearest live enemy. */
function autoFire(world: World) {
  const p = world.player;
  let best: Enemy | null = null;
  let bestD = Infinity;
  for (const e of world.enemies) {
    // Never auto-target a decoy or a charmed ally.
    if (e.arena !== world.arena || e.isClone || e.charmed) continue;
    const d = dist2(e.pos, p.pos);
    if (d < bestD) {
      bestD = d;
      best = e;
    }
  }
  if (!best) return;
  const a = Math.atan2(best.pos.y - p.pos.y, best.pos.x - p.pos.x);
  const spd = bulletSpeed(world.load);
  world.bullets.push({
    id: world.nextId++,
    pos: { ...p.pos },
    vel: { x: Math.cos(a) * spd, y: Math.sin(a) * spd },
    life: bulletLife(world.load, 1.1),
  });
}

/** Resolve a player bullet striking enemy `e`, honoring the active special. */
function applyBulletHit(world: World, e: Enemy, at: Vec) {
  const load = world.load;
  if (load.special === "love") {
    // Love bullets convert instead of damage: try to charm the enemy.
    tryCharm(world, e);
    burst(world, at, LOVE_COLOR, 5);
    return;
  }
  const dmg = bulletDamage(load);
  if (load.special === "electric") {
    electricArc(world, e, dmg); // chain a share to neighbors first (uses its pos)
    burst(world, at, ELECTRIC_COLOR, 5);
  } else {
    burst(world, at, COLORS.cyan, 4);
  }
  damageEnemy(world, e, dmg);
}

/** Electric chain: deal a fraction of the hit's damage to every other live
 *  enemy within reach of the struck one, with a little arc of sparks. */
function electricArc(world: World, primary: Enemy, dmg: number) {
  const origin = { ...primary.pos };
  const r2 = ELECTRIC_RADIUS * ELECTRIC_RADIUS;
  for (const o of world.enemies) {
    if (o === primary || o.arena !== world.arena || o.isClone || o.charmed) continue;
    if (dist2(o.pos, origin) <= r2) {
      burst(world, o.pos, ELECTRIC_COLOR, 6);
      damageEnemy(world, o, dmg * ELECTRIC_SHARE);
    }
  }
}

/** Love bullet: try to win an enemy over. The more health it has, the harder —
 *  bosses and clones are immune. A charmed enemy fights the swarm for a while. */
function tryCharm(world: World, e: Enemy) {
  if (e.isBoss || e.isClone || e.charmed) return;
  const chance = Math.min(0.9, CHARM_BASE / Math.max(1, e.hp));
  if (Math.random() < chance) {
    e.charmed = true;
    e.charmTimer = CHARM_DURATION;
    e.hitFlash = 1;
    floatText(world, e.pos, "♥", LOVE_COLOR);
    burst(world, e.pos, LOVE_COLOR, 14);
  } else {
    floatText(world, e.pos, "…", LOVE_COLOR);
  }
}

/** Drive a charmed ally: chase the nearest hostile and brawl on contact (both
 *  sides take damage — this is also how the swarm "targets" charmed units). It
 *  poofs when its charm timer runs out so allies can't pile up forever. */
function stepCharmed(world: World, e: Enemy, edt: number) {
  e.charmTimer -= edt;
  if (e.charmTimer <= 0) {
    world.enemies = world.enemies.filter((x) => x !== e);
    burst(world, e.pos, LOVE_COLOR, 12);
    return;
  }
  let best: Enemy | null = null;
  let bd = Infinity;
  for (const o of world.enemies) {
    if (o === e || o.arena !== world.arena || o.charmed || o.isClone) continue;
    const d = dist2(o.pos, e.pos);
    if (d < bd) {
      bd = d;
      best = o;
    }
  }
  if (!best) {
    // No one to fight — drift and bounce.
    e.pos.x += e.vel.x * edt;
    e.pos.y += e.vel.y * edt;
    bounce(world, e);
    return;
  }
  homeToward(e, best.pos, e.speed * 1.15, edt, 3);
  const rr = (e.radius + best.radius) * (e.radius + best.radius);
  if (dist2(e.pos, best.pos) <= rr) {
    damageEnemy(world, best, e.contactDmg + 1); // your ally bites
    damageEnemy(world, e, best.contactDmg); // and the swarm bites back
    const d = Math.hypot(best.pos.x - e.pos.x, best.pos.y - e.pos.y) || 1;
    e.pos.x -= ((best.pos.x - e.pos.x) / d) * PLAYER_KNOCKBACK;
    e.pos.y -= ((best.pos.y - e.pos.y) / d) * PLAYER_KNOCKBACK;
  }
}

/** Nearest charmed ally in the same sector as `e` (for swarm re-targeting). */
function nearestCharmed(world: World, e: Enemy): Enemy | null {
  let best: Enemy | null = null;
  let bd = Infinity;
  for (const o of world.enemies) {
    if (!o.charmed || o.arena !== e.arena) continue;
    const d = dist2(o.pos, e.pos);
    if (d < bd) {
      bd = d;
      best = o;
    }
  }
  return best;
}

/** Whether a boss is currently alive (gates bomb-planting and sector-leaving). */
export function bossActive(world: World): boolean {
  return world.enemies.some((e) => e.isBoss && !e.charmed);
}

/** Bullets emitted per click once the Sidearm is owned (0 otherwise). */
export function bulletsPerClick(load: Loadout): number {
  return load.canShoot ? 3 + 2 * load.fireRateLevel : 0;
}

function fireBurst(world: World) {
  const n = bulletsPerClick(world.load);
  const off = Math.random() * Math.PI * 2;
  const spd = bulletSpeed(world.load);
  const life = bulletLife(world.load, 0.9);
  for (let i = 0; i < n; i++) {
    const a = off + (i / n) * Math.PI * 2;
    world.bullets.push({
      id: world.nextId++,
      pos: { ...world.player.pos },
      vel: { x: Math.cos(a) * spd, y: Math.sin(a) * spd },
      life,
    });
  }
}

function stepWave(world: World, dt: number) {
  world.waveBanner = Math.max(0, world.waveBanner - dt);
  const arena = world.arena;
  const st = world.arenas[arena];
  if (st.pending > 0) {
    st.spawnTimer -= dt;
    // Cap the simultaneous live enemies in the sector — keeps a big early batch
    // trickling in instead of swarming all at once (anti-lag, gentler ramp).
    const aliveHere = world.enemies.reduce((n, e) => (e.arena === arena ? n + 1 : n), 0);
    if (st.spawnTimer <= 0 && aliveHere < MAX_ACTIVE_ENEMIES) {
      spawnEnemy(world, st.queue.pop() ?? "clock", arena);
      st.pending--;
      st.spawnTimer = spawnInterval(world.wave);
    }
  } else if (!world.enemies.some((e) => e.arena === arena && !e.charmed)) {
    // A lingering charmed ally doesn't hold the wave open.
    world.wave++; // clearing the active sector advances the shared wave level
    setupWave(world, arena, world.wave % 10 === 0); // every 10th wave is a boss
  }
}

function stepEnemies(world: World, edt: number) {
  const wave = world.wave;
  const p = world.player;

  for (const e of world.enemies) {
    if (e.arena !== world.arena) continue; // off-sector enemies are frozen
    e.spin += e.spinRate * edt;
    e.hitFlash = Math.max(0, e.hitFlash - edt * 4);
    e.flipAnim = Math.max(0, e.flipAnim - edt);
    e.reload -= edt;

    // Charmed allies run their own brawl AI and never touch the player.
    if (e.charmed) {
      stepCharmed(world, e, edt);
      continue;
    }

    // Boss signature dash overrides normal movement while it's lunging/charging.
    const dashing = bossDashes(e) && stepBossDash(world, e, edt);

    if (dashing) {
      // movement handled by stepBossDash
    } else if (e.kind === "hunter") {
      // The plain enemy: chase the cursor — or the nearest charmed ally if one is
      // closer (so the swarm visibly turns on your converts) — and ram it.
      const ally = nearestCharmed(world, e);
      const target =
        ally && dist2(ally.pos, e.pos) < dist2(p.pos, e.pos) ? ally.pos : p.pos;
      homeToward(e, target, e.speed, edt, 3.5);
    } else if (e.kind === "shooter") {
      // Hold mid-range and fire aimed bolts at the cursor.
      const d = Math.hypot(p.pos.x - e.pos.x, p.pos.y - e.pos.y) || 1;
      const sign = d > 260 ? 1 : d < 170 ? -1 : 0;
      e.pos.x += ((p.pos.x - e.pos.x) / d) * e.speed * sign * edt;
      e.pos.y += ((p.pos.y - e.pos.y) / d) * e.speed * sign * edt;
      if (e.reload <= 0) {
        e.reload = e.reloadTime;
        const n = e.isBoss ? 3 : 1; // boss fires a small spread
        for (let i = 0; i < n; i++) fireBolt(world, e, p.pos, (i - (n - 1) / 2) * 0.22);
      }
    } else if (e.kind === "clock") {
      // Drift toward a slowly-roaming target.
      e.wanderTimer -= edt;
      if (e.wanderTimer <= 0) {
        e.wander = { x: 60 + Math.random() * (world.w - 120), y: 60 + Math.random() * (world.h - 120) };
        e.wanderTimer = 2 + Math.random() * 2;
      }
      steerToward(e, e.wander, e.speed, edt);
      if (e.isClone) {
        // A decoy: it just drifts. It never fires (the firing tell) and never hurts.
      } else if (e.isBoss) {
        stepClockBoss(world, e, edt); // teleport + clone cycle, on top of hands
        if (e.reload <= 0) {
          e.reload = Math.max(1.1, e.reloadTime - wave * 0.04);
          throwHands(world, e);
        }
      } else if (e.reload <= 0) {
        // Regular clock: hurl its hands at the cursor; they regrow over the reload.
        e.reload = Math.max(1.1, e.reloadTime - wave * 0.04);
        throwHands(world, e);
      }
    } else if (e.kind === "dasher") {
      // Stalk slowly, telegraph, then lunge fast at the cursor and coast.
      if (e.dashTime > 0) {
        e.dashTime -= edt;
        e.pos.x += e.vel.x * edt;
        e.pos.y += e.vel.y * edt;
        bounce(world, e);
      } else if (e.windup > 0) {
        e.windup -= edt;
        e.aimAngle = Math.atan2(p.pos.y - e.pos.y, p.pos.x - e.pos.x); // aim tracks until launch
        e.vel.x *= 0.8;
        e.vel.y *= 0.8;
        e.pos.x += e.vel.x * edt;
        e.pos.y += e.vel.y * edt;
        if (e.windup <= 0) {
          const ds = e.speed * DASH_MULT * (e.isBoss ? 3.2 : 1); // boss = far longer lunge
          e.vel = { x: Math.cos(e.aimAngle) * ds, y: Math.sin(e.aimAngle) * ds };
          e.dashTime = DASH_TIME * (e.isBoss ? 2.2 : 1);
        }
      } else {
        homeToward(e, p.pos, e.speed, edt, 2);
        if (e.reload <= 0) {
          e.windup = DASH_WINDUP * (e.isBoss ? 0.5 : 1);
          e.reload = e.reloadTime;
        }
      }
    } else if (e.kind === "beamer") {
      // Hold mid-range, charge (telegraph) while tracking, then LOCK the aim for
      // a final window and fire along the locked angle — never the live cursor —
      // so the shot is dodgeable instead of a guaranteed hit.
      const d = Math.hypot(p.pos.x - e.pos.x, p.pos.y - e.pos.y) || 1;
      if (e.windup <= 0) {
        e.armed = false;
        const sign = d > 320 ? 1 : d < 210 ? -1 : 0;
        e.pos.x += ((p.pos.x - e.pos.x) / d) * e.speed * sign * edt;
        e.pos.y += ((p.pos.y - e.pos.y) / d) * e.speed * sign * edt;
        if (e.reload <= 0) e.windup = BEAM_WINDUP * (e.isBoss ? 0.7 : 1);
      } else {
        e.windup -= edt;
        // Track the cursor only until the lock window; after that the aim is
        // frozen (armed) and the player has those seconds to slip off the line.
        if (e.windup > BEAM_LOCK) {
          e.aimAngle = Math.atan2(p.pos.y - e.pos.y, p.pos.x - e.pos.x);
        } else {
          e.armed = true;
        }
        if (e.windup <= 0) {
          fireBeam(world, e, e.aimAngle);
          e.armed = false;
          e.reload = e.reloadTime;
        }
      }
    } else {
      // Hourglass + shard: harmless at first — drift and flip heading. But each
      // flip is counted, and once it has flipped enough times it turns deadly:
      // telegraph, then LUNGE at the cursor, pause, and do it again. Shards (the
      // mini ones) flip-to-aggressive sooner and lunge faster.
      const shard = e.kind === "shard";
      const flipsToDash = shard ? SHARD_FLIPS_TO_DASH : HG_FLIPS_TO_DASH;
      if (e.dashTime > 0) {
        // Mid-lunge: coast along the locked aim.
        e.dashTime -= edt;
        e.pos.x += e.vel.x * edt;
        e.pos.y += e.vel.y * edt;
        bounce(world, e);
      } else if (e.windup > 0) {
        // Telegraphing a lunge: slow to a near-stop, aim tracks until launch.
        e.windup -= edt;
        e.aimAngle = Math.atan2(p.pos.y - e.pos.y, p.pos.x - e.pos.x);
        e.vel.x *= 0.8;
        e.vel.y *= 0.8;
        e.pos.x += e.vel.x * edt;
        e.pos.y += e.vel.y * edt;
        if (e.windup <= 0) {
          const ds = e.speed * (shard ? SHARD_DASH_MULT : HG_DASH_MULT);
          e.vel = { x: Math.cos(e.aimAngle) * ds, y: Math.sin(e.aimAngle) * ds };
          e.dashTime = HG_DASH_TIME;
          e.reload = HG_DASH_CD; // pause before the next lunge
        }
      } else if (e.flips >= flipsToDash && e.reload <= 0) {
        // Earned its aggression — wind up the next lunge.
        e.windup = shard ? SHARD_DASH_WINDUP : HG_DASH_WINDUP;
      } else {
        // Passive phase: drift and flip heading, tallying flips toward the dash.
        e.flipTimer -= edt;
        if (e.flipTimer <= 0) {
          e.flipTimer = shard ? 0.55 + Math.random() * 0.6 : 0.9 + Math.random() * 1.1;
          e.flips++;
          e.flipAnim = HG_FLIP_DUR; // play the literal flip (squash + reopen)
          const a = Math.random() * Math.PI * 2;
          e.vel = { x: Math.cos(a) * e.speed, y: Math.sin(a) * e.speed };
        }
        e.pos.x += e.vel.x * edt;
        e.pos.y += e.vel.y * edt;
        bounce(world, e);
      }
    }

    // Contact damage — touching the cursor costs hearts (gated by i-frames), then
    // the enemy is shoved off so it can't sit on you. Clones are illusions: no hit.
    if (p.invuln <= 0 && !e.isClone) {
      const rr = (e.radius + PLAYER_R) * (e.radius + PLAYER_R);
      if (dist2(e.pos, p.pos) <= rr) {
        hurtPlayer(world, false, e.contactDmg);
        const d = Math.hypot(p.pos.x - e.pos.x, p.pos.y - e.pos.y) || 1;
        e.pos.x -= ((p.pos.x - e.pos.x) / d) * PLAYER_KNOCKBACK;
        e.pos.y -= ((p.pos.y - e.pos.y) / d) * PLAYER_KNOCKBACK;
      }
    }
  }
}

function homeToward(e: Enemy, target: Vec, speed: number, edt: number, accel: number) {
  const dx = target.x - e.pos.x;
  const dy = target.y - e.pos.y;
  const len = Math.hypot(dx, dy) || 1;
  e.vel.x += ((dx / len) * speed - e.vel.x) * Math.min(1, edt * accel);
  e.vel.y += ((dy / len) * speed - e.vel.y) * Math.min(1, edt * accel);
  e.pos.x += e.vel.x * edt;
  e.pos.y += e.vel.y * edt;
}

function steerToward(e: Enemy, target: Vec, speed: number, edt: number) {
  const dx = target.x - e.pos.x;
  const dy = target.y - e.pos.y;
  const len = Math.hypot(dx, dy) || 1;
  e.vel.x += ((dx / len) * speed - e.vel.x) * Math.min(1, edt * 2);
  e.vel.y += ((dy / len) * speed - e.vel.y) * Math.min(1, edt * 2);
  e.pos.x += e.vel.x * edt;
  e.pos.y += e.vel.y * edt;
}

/** A clock hurls its hands (hour / minute / second) at the cursor as spinning
 *  rods. They regrow on the clock's body over its reload (drawn shorter while
 *  regenerating). A boss throws a wider fan and its hands hit for double. */
function throwHands(world: World, e: Enemy) {
  const aim = Math.atan2(world.player.pos.y - e.pos.y, world.player.pos.x - e.pos.x);
  const lens = [e.radius * 0.55, e.radius * 0.82, e.radius * 1.05]; // hour, minute, second
  const spreads = e.isBoss ? [-0.5, -0.25, 0, 0.25, 0.5] : [-0.2, 0, 0.2];
  const dmg = e.isBoss ? 2 : 1;
  for (let i = 0; i < spreads.length; i++) {
    const a = aim + spreads[i];
    world.spikes.push({
      id: world.nextId++,
      pos: { ...e.pos },
      vel: { x: Math.cos(a) * CLOCK_HAND_SPEED, y: Math.sin(a) * CLOCK_HAND_SPEED },
      radius: SPIKE_R + 2,
      life: 4,
      dmg,
      len: lens[i % lens.length],
      spin: a,
      spinRate: (Math.random() < 0.5 ? -1 : 1) * (3 + Math.random() * 3),
      color: ENEMY_COLOR.clock,
    });
  }
  burst(world, e.pos, ENEMY_COLOR.clock, 8);
}

/** The clock boss's signature: every cycle it teleports (sometimes right onto
 *  the player) and conjures damage-less clones, so you can't tell which is real —
 *  except the real one is the only one still throwing hands. */
function stepClockBoss(world: World, e: Enemy, edt: number) {
  e.cloneCd -= edt;
  if (e.cloneCd <= 0) {
    e.cloneCd = CLOCK_CLONE_CD;
    clockBlink(world, e);
    conjureClones(world, e);
  }
}

/** Teleport the real clock boss — half the time it blinks in next to the player. */
function clockBlink(world: World, e: Enemy) {
  burst(world, e.pos, ENEMY_COLOR.clock, 20); // vanish puff
  if (Math.random() < CLOCK_TP_NEAR_CHANCE) {
    const a = Math.random() * Math.PI * 2;
    const r = CLOCK_TP_NEAR_DIST * (0.7 + Math.random() * 0.6);
    e.pos = {
      x: clamp(world.player.pos.x + Math.cos(a) * r, e.radius, world.w - e.radius),
      y: clamp(world.player.pos.y + Math.sin(a) * r, e.radius, world.h - e.radius),
    };
  } else {
    e.pos = {
      x: e.radius + Math.random() * (world.w - 2 * e.radius),
      y: e.radius + Math.random() * (world.h - 2 * e.radius),
    };
  }
  e.vel = { x: 0, y: 0 };
  burst(world, e.pos, ENEMY_COLOR.clock, 20); // reappear puff
  world.shake = Math.max(world.shake, 12);
}

/** Replace the decoys: clear the old clones in the boss's sector and conjure a
 *  fresh set at random spots (each an invulnerable, damage-less look-alike). */
function conjureClones(world: World, e: Enemy) {
  world.enemies = world.enemies.filter((x) => !(x.isClone && x.arena === e.arena));
  for (let i = 0; i < CLOCK_CLONE_COUNT; i++) {
    const at = {
      x: e.radius + Math.random() * (world.w - 2 * e.radius),
      y: e.radius + Math.random() * (world.h - 2 * e.radius),
    };
    spawnEnemy(world, "clock", e.arena, { at, clone: true });
  }
}

function fireBolt(world: World, e: Enemy, target: Vec, spreadRad: number) {
  const base = Math.atan2(target.y - e.pos.y, target.x - e.pos.x) + spreadRad;
  world.spikes.push({
    id: world.nextId++,
    pos: { ...e.pos },
    vel: { x: Math.cos(base) * BOLT_SPEED, y: Math.sin(base) * BOLT_SPEED },
    radius: SPIKE_R + 1,
    life: 4,
  });
}

/** Bosses without their own dash/beam get a signature lunge. (dasher/beamer
 *  bosses have an amplified version of their own; the clock boss teleports +
 *  conjures clones instead, and clones never dash.) */
function bossDashes(e: Enemy): boolean {
  return (
    e.isBoss &&
    !e.isClone &&
    (e.kind === "hunter" || e.kind === "shooter" || e.kind === "hourglass")
  );
}

/** Run a boss's periodic dash. Returns true while it's telegraphing or lunging
 *  (the caller then skips the kind's normal movement for this frame). */
function stepBossDash(world: World, e: Enemy, edt: number): boolean {
  const p = world.player;
  if (e.dashTime > 0) {
    e.dashTime -= edt;
    e.pos.x += e.vel.x * edt;
    e.pos.y += e.vel.y * edt;
    bounce(world, e);
    return true;
  }
  if (e.windup > 0) {
    e.windup -= edt;
    e.aimAngle = Math.atan2(p.pos.y - e.pos.y, p.pos.x - e.pos.x);
    if (e.windup <= 0) {
      const ds = e.speed * BOSS_DASH_MULT;
      e.vel = { x: Math.cos(e.aimAngle) * ds, y: Math.sin(e.aimAngle) * ds };
      e.dashTime = BOSS_DASH_TIME;
    }
    return true;
  }
  e.dashCd -= edt;
  if (e.dashCd <= 0) {
    e.dashCd = BOSS_DASH_CD;
    e.windup = BOSS_DASH_WINDUP;
    return true;
  }
  return false;
}

/** Fire a beamer's laser along `angle`. A boss beamer fires a 3-beam fan. */
function fireBeam(world: World, e: Enemy, angle: number) {
  const spread = e.isBoss ? [-0.26, 0, 0.26] : [0];
  for (const off of spread) {
    world.beams.push({
      id: world.nextId++,
      pos: { ...e.pos },
      angle: angle + off,
      len: BEAM_LEN,
      life: BEAM_LIFE,
      maxLife: BEAM_LIFE,
      width: BEAM_WIDTH * (e.isBoss ? 1.4 : 1),
      dmg: e.contactDmg,
    });
  }
}

function stepBeams(world: World, edt: number) {
  const p = world.player;
  const kept: Beam[] = [];
  for (const b of world.beams) {
    b.life -= edt;
    if (b.life <= 0) continue;
    if (p.invuln <= 0) {
      const end = { x: b.pos.x + Math.cos(b.angle) * b.len, y: b.pos.y + Math.sin(b.angle) * b.len };
      if (distToSegment(p.pos, b.pos, end) <= b.width / 2 + PLAYER_R) hurtPlayer(world, false, b.dmg);
    }
    kept.push(b);
  }
  world.beams = kept;
}

/** Shortest distance from point `p` to the segment `a`–`b`. */
function distToSegment(p: Vec, a: Vec, b: Vec): number {
  const dx = b.x - a.x;
  const dy = b.y - a.y;
  const len2 = dx * dx + dy * dy || 1;
  const t = clamp(((p.x - a.x) * dx + (p.y - a.y) * dy) / len2, 0, 1);
  return Math.hypot(p.x - (a.x + t * dx), p.y - (a.y + t * dy));
}

function bounce(world: World, e: Enemy) {
  if (e.pos.x < e.radius) {
    e.pos.x = e.radius;
    e.vel.x = Math.abs(e.vel.x);
  }
  if (e.pos.x > world.w - e.radius) {
    e.pos.x = world.w - e.radius;
    e.vel.x = -Math.abs(e.vel.x);
  }
  if (e.pos.y < e.radius) {
    e.pos.y = e.radius;
    e.vel.y = Math.abs(e.vel.y);
  }
  if (e.pos.y > world.h - e.radius) {
    e.pos.y = world.h - e.radius;
    e.vel.y = -Math.abs(e.vel.y);
  }
}

function stepSpikes(world: World, edt: number) {
  const p = world.player;
  const kept = [];
  for (const s of world.spikes) {
    s.pos.x += s.vel.x * edt;
    s.pos.y += s.vel.y * edt;
    s.life -= edt;
    if (s.spinRate) s.spin = (s.spin ?? 0) + s.spinRate * edt; // tumble the clock-hands
    if (s.life <= 0 || s.pos.x < -40 || s.pos.x > world.w + 40 || s.pos.y < -40 || s.pos.y > world.h + 40)
      continue;
    const rr = (s.radius + PLAYER_R) * (s.radius + PLAYER_R);
    if (p.invuln <= 0 && dist2(s.pos, p.pos) <= rr) {
      hurtPlayer(world, false, s.dmg ?? 1);
      continue; // spike is consumed by the hit
    }
    kept.push(s);
  }
  world.spikes = kept;
}

function stepBullets(world: World, dt: number) {
  const kept = [];
  for (const b of world.bullets) {
    b.pos.x += b.vel.x * dt;
    b.pos.y += b.vel.y * dt;
    b.life -= dt;
    if (b.life <= 0 || b.pos.x < 0 || b.pos.x > world.w || b.pos.y < 0 || b.pos.y > world.h) continue;
    let hit = false;
    for (const e of world.enemies) {
      // Bullets pass through decoys and your own charmed allies.
      if (e.arena !== world.arena || e.isClone || e.charmed) continue;
      const rr = (BULLET_R + e.radius) * (BULLET_R + e.radius);
      if (dist2(b.pos, e.pos) <= rr) {
        applyBulletHit(world, e, b.pos);
        hit = true;
        break;
      }
    }
    if (!hit) kept.push(b);
  }
  world.bullets = kept;
}

function stepBombs(world: World, dt: number) {
  // Plant a new bomb on a timer (biased toward a sector you're not in, so it
  // creates a nav alert). Fuses burn in every sector at once. No new bombs while
  // a boss is alive — the boss is a self-contained duel in its own sector.
  world.bombTimer -= dt;
  if (world.bombTimer <= 0 && world.bombs.length < MAX_BOMBS && !bossActive(world)) {
    world.bombTimer = bombInterval(world.wave);
    plantBomb(world);
  }
  const kept: Bomb[] = [];
  for (const b of world.bombs) {
    // Dampening Field slows the fuse while you're actively defusing this bomb.
    const burn = b.defusing
      ? Math.max(DEFUSE_BURN_MIN, 1 - DEFUSE_FREEZE_STEP * world.load.defuseFreezeLevel)
      : 1;
    b.fuse -= dt * burn;
    if (b.fuse <= 0) {
      // Detonate. Letting bombs blow builds a streak that escalates the damage
      // from 1 heart up to BOMB_FAIL_DMG_MAX; defusing one resets it.
      world.bombStreak++;
      const dmg = Math.min(BOMB_FAIL_DMG_MAX, world.bombStreak);
      world.shake = 20 + dmg * 3;
      burst(world, b.pos, COLORS.pink, 22 + dmg * 6);
      floatText(world, b.pos, `-${dmg}`, COLORS.pink);
      hurtPlayer(world, true, dmg);
      continue;
    }
    kept.push(b);
  }
  world.bombs = kept;
}

function plantBomb(world: World) {
  // Only plant in UNLOCKED sectors (you must be able to reach it), biased to a
  // non-active one so it creates a nav alert.
  const unlocked = unlockedSectorIds(world.wave);
  const others = unlocked.filter((id) => id !== world.arena);
  const pool = others.length > 0 && Math.random() < 0.8 ? others : unlocked;
  const arena = pool[Math.floor(Math.random() * pool.length)] ?? world.arena;
  // Long Fuse adds seconds to the fuse; Quick Hands trims the hold-to-defuse.
  const fuse = BOMB_FUSE + DEFUSE_WINDOW_STEP * world.load.defuseWindowLevel;
  const baseDefuse = DEFUSE_MIN + Math.random() * (DEFUSE_MAX - DEFUSE_MIN);
  const defuseTime = Math.max(
    DEFUSE_TIME_MIN,
    baseDefuse * (1 - DEFUSE_SPEED_STEP * world.load.defuseSpeedLevel),
  );
  world.bombs.push({
    id: world.nextId++,
    arena,
    pos: { x: 80 + Math.random() * (world.w - 160), y: 110 + Math.random() * (world.h - 220) },
    fuse,
    maxFuse: fuse,
    defuse: 0,
    defuseTime,
    radius: BOMB_R,
    defusing: false,
  });
}

function spawnPickup(world: World, arena: ArenaId, at: Vec, kind: "health", value: number) {
  world.pickups.push({
    id: world.nextId++,
    arena,
    kind,
    pos: { ...at },
    value,
    life: PICKUP_LIFE,
    maxLife: PICKUP_LIFE,
    bob: Math.random() * Math.PI * 2,
  });
}

function stepPickups(world: World, dt: number) {
  const p = world.player;
  const kept = [];
  for (const pk of world.pickups) {
    pk.life -= dt;
    pk.bob += dt * 3;
    if (pk.life <= 0) continue;
    // Only collectable in its own sector; walk the cursor over it to grab it.
    if (pk.arena === world.arena) {
      const rr = (PICKUP_R + PLAYER_R + 6) * (PICKUP_R + PLAYER_R + 6);
      if (dist2(pk.pos, p.pos) <= rr) {
        const healed = Math.min(pk.value, world.player.maxHealth - world.player.health);
        if (healed > 0) {
          world.player.health += healed;
          floatText(world, pk.pos, `+${healed} HP`, COLORS.green);
        } else {
          floatText(world, pk.pos, "FULL HP", COLORS.green);
        }
        burst(world, pk.pos, COLORS.green, 16);
        continue; // consumed
      }
    }
    kept.push(pk);
  }
  world.pickups = kept;
}

function stepEffects(world: World, dt: number) {
  world.particles = world.particles.filter((p) => {
    p.pos.x += p.vel.x * dt;
    p.pos.y += p.vel.y * dt;
    p.vel.x *= 0.92;
    p.vel.y *= 0.92;
    p.life -= dt;
    return p.life > 0;
  });
  world.zaps = world.zaps.filter((z) => {
    z.life -= dt;
    return z.life > 0;
  });
  world.floats = world.floats.filter((f) => {
    f.pos.y += f.vel.y * dt;
    f.life -= dt;
    return f.life > 0;
  });
}

// ── Damage & death ───────────────────────────────────────────────────────────
function damageEnemy(world: World, e: Enemy, amount: number) {
  if (e.hp <= 0 || e.isClone) return; // decoys are invulnerable
  e.hp -= amount;
  e.hitFlash = 1;
  if (e.hp <= 0) killEnemy(world, e);
}

function killEnemy(world: World, e: Enemy) {
  // Killing the real clock boss dispels all of its lingering decoys.
  world.enemies = world.enemies.filter(
    (x) => x !== e && !(e.isBoss && !e.isClone && x.isClone && x.arena === e.arena),
  );
  const color = ENEMY_COLOR[e.kind];
  burst(world, e.pos, color, e.isBoss ? 40 : e.kind === "clock" ? 16 : 10);
  world.shake = Math.min(e.isBoss ? 26 : 14, world.shake + (e.isBoss ? 24 : e.kind === "clock" ? 8 : 4));

  const pts = Math.floor(
    ENEMY[e.kind].points * (1 + 0.05 * (world.wave - 1)) * world.load.scoreMult * (e.isBoss ? 5 : 1),
  );
  world.score += pts;
  floatText(world, e.pos, e.isBoss ? `BOSS +${pts}` : `+${pts}`, color);

  // A defeated boss drops a health pack where it died — go grab it to heal.
  // Any other enemy has a small (5%) chance to drop a single-heart orb.
  if (e.isBoss) spawnPickup(world, e.arena, e.pos, "health", HEALTH_PACK_VALUE);
  else if (Math.random() < 0.05) spawnPickup(world, e.arena, e.pos, "health", 1);

  // A (non-boss) hourglass splits into two fast shards in the same sector.
  if (e.kind === "hourglass" && !e.isBoss) {
    spawnEnemy(world, "shard", e.arena, { at: { x: e.pos.x - 12, y: e.pos.y } });
    spawnEnemy(world, "shard", e.arena, { at: { x: e.pos.x + 12, y: e.pos.y } });
  }
}

function defuseBomb(world: World, b: Bomb) {
  world.bombs = world.bombs.filter((x) => x !== b);
  world.bombStreak = 0; // a successful defuse breaks the failure streak
  burst(world, b.pos, COLORS.green, 18);
  const pts = Math.floor(BOMB_POINTS * world.load.scoreMult);
  world.score += pts;
  floatText(world, b.pos, `DEFUSED +${pts}`, COLORS.green);
  // Defuser Pusher: if charged, the defuse releases a non-damaging shockwave that
  // shoves every enemy in the sector outward. Then it goes on cooldown (1 min).
  if (world.pusher.cooldown <= 0) {
    pusherShock(world, b.pos);
    world.pusher.cooldown = world.pusher.interval;
  }
}

/** The Defuser Pusher blast: a big cyan ring + an outward shove on every live
 *  enemy in the active sector. Deals no damage; it just buys breathing room and
 *  interrupts any wind-up/lunge in progress. */
function pusherShock(world: World, origin: Vec) {
  world.zaps.push({ pos: { ...origin }, life: 0.5, maxLife: 0.5, radius: PUSHER_RADIUS });
  world.shake = Math.max(world.shake, 14);
  floatText(world, origin, "PUSH!", COLORS.cyan);
  for (const e of world.enemies) {
    if (e.arena !== world.arena) continue;
    const dx = e.pos.x - origin.x;
    const dy = e.pos.y - origin.y;
    const d = Math.hypot(dx, dy) || 1;
    e.pos.x = clamp(e.pos.x + (dx / d) * PUSHER_SHOVE, e.radius, world.w - e.radius);
    e.pos.y = clamp(e.pos.y + (dy / d) * PUSHER_SHOVE, e.radius, world.h - e.radius);
    e.vel.x += (dx / d) * PUSHER_IMPULSE;
    e.vel.y += (dy / d) * PUSHER_IMPULSE;
    e.windup = 0; // interrupt any telegraphed attack
    e.dashTime = 0;
    e.armed = false;
  }
  burst(world, origin, COLORS.cyan, 26);
}

function hurtPlayer(world: World, ignoreInvuln = false, amount = 1) {
  const p = world.player;
  if (p.invuln > 0 && !ignoreInvuln) return;
  p.health -= amount;
  p.invuln = INVULN;
  p.hurt = 0.5;
  world.shake = Math.max(world.shake, 16);
  burst(world, p.pos, COLORS.pink, 14);
}
