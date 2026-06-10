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
const BULLET_SPEED = 560;
const BULLET_R = 5;
const BULLET_DMG = 1;
const SPIKE_R = 6;
const SLOW_FACTOR = 0.32; // enemy/spike time multiplier during Overclock

const BOMB_R = 22;
const BOMB_FUSE = 12; // seconds before a planted bomb blows
const BOMB_GAP = 15; // seconds between bomb plantings
const MAX_BOMBS = 2;
const BOMB_POINTS = 50;
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

// Beamer laser. Charges (telegraph) tracking the cursor, then fires a straight
// beam that lingers briefly. Bosses charge faster and fire a fan.
const BEAM_WINDUP = 0.85;
const BEAM_LIFE = 0.16;
const BEAM_LEN = 1400;
const BEAM_WIDTH = 11;

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
    autoFireCd: 0,
    arena: "library", // synced to the real route on mount
    enemies: [],
    spikes: [],
    beams: [],
    bullets: [],
    bombs: [],
    particles: [],
    zaps: [],
    floats: [],
    arenas,
    wave,
    bombTimer: BOMB_GAP,
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
    // Boss wave: the sector's headline enemy, beefed, plus a few minions.
    spawnEnemy(world, pool[0], arena, { boss: true });
    world.bossBanner = 3.6;
    const minions = 3;
    st.queue = Array.from({ length: minions }, (_, i) => pool[i % pool.length]);
  } else {
    const count = 2 + Math.floor(world.wave * 0.8);
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
  opts: { at?: Vec; boss?: boolean } = {},
) {
  const base = ENEMY[kind];
  const boss = opts.boss ?? false;
  const pos = opts.at ?? edgePoint(world);
  const ang = Math.random() * Math.PI * 2;
  const waveScale = 1 + (world.wave - 1) * 0.05;
  const hp = Math.max(1, Math.round(base.hp * waveScale)) * (boss ? 12 : 1);
  const speed = base.speed * (boss ? 0.85 : 1);
  const reloadTime = base.reload * (boss ? 0.55 : 1);
  world.enemies.push({
    id: world.nextId++,
    kind,
    arena,
    pos,
    vel: { x: Math.cos(ang) * speed, y: Math.sin(ang) * speed },
    hp,
    maxHp: hp,
    radius: base.r * (boss ? 1.9 : 1),
    speed,
    contactDmg: base.contact * (boss ? 2 : 1),
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
    dashTime: 0,
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

  stepPlayer(world, dt, input);
  stepWave(world, dt);
  stepEnemies(world, edt);
  stepSpikes(world, edt);
  stepBeams(world, edt);
  stepBullets(world, dt);
  stepBombs(world, dt);
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
      if (e.arena !== world.arena) continue;
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
    if (e.arena !== world.arena) continue;
    const d = dist2(e.pos, p.pos);
    if (d < bestD) {
      bestD = d;
      best = e;
    }
  }
  if (!best) return;
  const a = Math.atan2(best.pos.y - p.pos.y, best.pos.x - p.pos.x);
  world.bullets.push({
    id: world.nextId++,
    pos: { ...p.pos },
    vel: { x: Math.cos(a) * BULLET_SPEED, y: Math.sin(a) * BULLET_SPEED },
    life: 1.1,
  });
}

/** Bullets emitted per click once the Sidearm is owned (0 otherwise). */
export function bulletsPerClick(load: Loadout): number {
  return load.canShoot ? 3 + 2 * load.fireRateLevel : 0;
}

function fireBurst(world: World) {
  const n = bulletsPerClick(world.load);
  const off = Math.random() * Math.PI * 2;
  for (let i = 0; i < n; i++) {
    const a = off + (i / n) * Math.PI * 2;
    world.bullets.push({
      id: world.nextId++,
      pos: { ...world.player.pos },
      vel: { x: Math.cos(a) * BULLET_SPEED, y: Math.sin(a) * BULLET_SPEED },
      life: 0.9,
    });
  }
}

function stepWave(world: World, dt: number) {
  world.waveBanner = Math.max(0, world.waveBanner - dt);
  const arena = world.arena;
  const st = world.arenas[arena];
  if (st.pending > 0) {
    st.spawnTimer -= dt;
    if (st.spawnTimer <= 0) {
      spawnEnemy(world, st.queue.pop() ?? "clock", arena);
      st.pending--;
      st.spawnTimer = 0.55;
    }
  } else if (!world.enemies.some((e) => e.arena === arena)) {
    world.wave++; // clearing the active sector advances the shared wave level
    setupWave(world, arena, world.wave % 10 === 0); // every 10th wave is a boss
  }
}

function stepEnemies(world: World, edt: number) {
  const wave = world.wave;
  const ringSpeed = 96 + wave * 6;
  const ring = Math.min(16, 6 + Math.floor(wave / 2));
  const p = world.player;

  for (const e of world.enemies) {
    if (e.arena !== world.arena) continue; // off-sector enemies are frozen
    e.spin += e.spinRate * edt;
    e.hitFlash = Math.max(0, e.hitFlash - edt * 4);
    e.reload -= edt;

    if (e.kind === "hunter") {
      // The plain enemy: chase the cursor and ram it.
      homeToward(e, p.pos, e.speed, edt, 3.5);
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
      // Drift toward a slowly-roaming target; radiate spike rings on cooldown.
      e.wanderTimer -= edt;
      if (e.wanderTimer <= 0) {
        e.wander = { x: 60 + Math.random() * (world.w - 120), y: 60 + Math.random() * (world.h - 120) };
        e.wanderTimer = 2 + Math.random() * 2;
      }
      steerToward(e, e.wander, e.speed, edt);
      if (e.reload <= 0) {
        e.reload = Math.max(1.1, e.reloadTime - wave * 0.04);
        emitRing(world, e, ring, ringSpeed);
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
          const ds = e.speed * DASH_MULT * (e.isBoss ? 1.5 : 1);
          e.vel = { x: Math.cos(e.aimAngle) * ds, y: Math.sin(e.aimAngle) * ds };
          e.dashTime = DASH_TIME * (e.isBoss ? 1.6 : 1);
        }
      } else {
        homeToward(e, p.pos, e.speed, edt, 2);
        if (e.reload <= 0) {
          e.windup = DASH_WINDUP * (e.isBoss ? 0.5 : 1);
          e.reload = e.reloadTime;
        }
      }
    } else if (e.kind === "beamer") {
      // Hold mid-range, charge (telegraph) while tracking, then fire a laser.
      const d = Math.hypot(p.pos.x - e.pos.x, p.pos.y - e.pos.y) || 1;
      if (e.windup <= 0) {
        const sign = d > 320 ? 1 : d < 210 ? -1 : 0;
        e.pos.x += ((p.pos.x - e.pos.x) / d) * e.speed * sign * edt;
        e.pos.y += ((p.pos.y - e.pos.y) / d) * e.speed * sign * edt;
        if (e.reload <= 0) e.windup = BEAM_WINDUP * (e.isBoss ? 0.6 : 1);
      } else {
        e.windup -= edt;
        e.aimAngle = Math.atan2(p.pos.y - e.pos.y, p.pos.x - e.pos.x);
        if (e.windup <= 0) {
          fireBeam(world, e, e.aimAngle);
          e.reload = e.reloadTime;
        }
      }
    } else {
      // Hourglass + shard: drift and flip heading unpredictably; shards lean
      // toward the player so they stay a threat.
      e.flipTimer -= edt;
      if (e.flipTimer <= 0) {
        e.flipTimer = e.kind === "shard" ? 0.7 + Math.random() : 1.1 + Math.random() * 1.4;
        if (e.kind === "shard") {
          const dx = p.pos.x - e.pos.x;
          const dy = p.pos.y - e.pos.y;
          const len = Math.hypot(dx, dy) || 1;
          const jitter = (Math.random() - 0.5) * 1.2;
          const ca = Math.cos(jitter);
          const sa = Math.sin(jitter);
          e.vel = {
            x: ((dx / len) * ca - (dy / len) * sa) * e.speed,
            y: ((dx / len) * sa + (dy / len) * ca) * e.speed,
          };
        } else {
          const a = Math.random() * Math.PI * 2;
          e.vel = { x: Math.cos(a) * e.speed, y: Math.sin(a) * e.speed };
        }
        e.spinRate = (Math.random() < 0.5 ? -1 : 1) * (0.6 + Math.random() * 1.4);
      }
      e.pos.x += e.vel.x * edt;
      e.pos.y += e.vel.y * edt;
      bounce(world, e);
    }

    // Contact damage — touching the cursor costs hearts (gated by i-frames), then
    // the enemy is shoved off so it can't sit on you.
    if (p.invuln <= 0) {
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

function emitRing(world: World, e: Enemy, ring: number, speed: number) {
  const off = Math.random() * Math.PI * 2;
  for (let i = 0; i < ring; i++) {
    const a = off + (i / ring) * Math.PI * 2;
    world.spikes.push({
      id: world.nextId++,
      pos: { ...e.pos },
      vel: { x: Math.cos(a) * speed, y: Math.sin(a) * speed },
      radius: SPIKE_R,
      life: 4,
    });
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
  if (e.pos.x < e.radius) (e.pos.x = e.radius), (e.vel.x = Math.abs(e.vel.x));
  if (e.pos.x > world.w - e.radius) (e.pos.x = world.w - e.radius), (e.vel.x = -Math.abs(e.vel.x));
  if (e.pos.y < e.radius) (e.pos.y = e.radius), (e.vel.y = Math.abs(e.vel.y));
  if (e.pos.y > world.h - e.radius) (e.pos.y = world.h - e.radius), (e.vel.y = -Math.abs(e.vel.y));
}

function stepSpikes(world: World, edt: number) {
  const p = world.player;
  const kept = [];
  for (const s of world.spikes) {
    s.pos.x += s.vel.x * edt;
    s.pos.y += s.vel.y * edt;
    s.life -= edt;
    if (s.life <= 0 || s.pos.x < -40 || s.pos.x > world.w + 40 || s.pos.y < -40 || s.pos.y > world.h + 40)
      continue;
    const rr = (s.radius + PLAYER_R) * (s.radius + PLAYER_R);
    if (p.invuln <= 0 && dist2(s.pos, p.pos) <= rr) {
      hurtPlayer(world);
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
      if (e.arena !== world.arena) continue;
      const rr = (BULLET_R + e.radius) * (BULLET_R + e.radius);
      if (dist2(b.pos, e.pos) <= rr) {
        damageEnemy(world, e, BULLET_DMG);
        burst(world, b.pos, COLORS.cyan, 4);
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
  // creates a nav alert). Fuses burn in every sector at once.
  world.bombTimer -= dt;
  if (world.bombTimer <= 0 && world.bombs.length < MAX_BOMBS) {
    world.bombTimer = BOMB_GAP;
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
      // Detonate — costs a heart wherever you are.
      world.shake = 20;
      burst(world, b.pos, COLORS.pink, 22);
      hurtPlayer(world, true);
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
  if (e.hp <= 0) return;
  e.hp -= amount;
  e.hitFlash = 1;
  if (e.hp <= 0) killEnemy(world, e);
}

function killEnemy(world: World, e: Enemy) {
  world.enemies = world.enemies.filter((x) => x !== e);
  const color = ENEMY_COLOR[e.kind];
  burst(world, e.pos, color, e.isBoss ? 40 : e.kind === "clock" ? 16 : 10);
  world.shake = Math.min(e.isBoss ? 26 : 14, world.shake + (e.isBoss ? 24 : e.kind === "clock" ? 8 : 4));

  const pts = Math.floor(
    ENEMY[e.kind].points * (1 + 0.05 * (world.wave - 1)) * world.load.scoreMult * (e.isBoss ? 5 : 1),
  );
  world.score += pts;
  floatText(world, e.pos, e.isBoss ? `BOSS +${pts}` : `+${pts}`, color);

  // A (non-boss) hourglass splits into two fast shards in the same sector.
  if (e.kind === "hourglass" && !e.isBoss) {
    spawnEnemy(world, "shard", e.arena, { at: { x: e.pos.x - 12, y: e.pos.y } });
    spawnEnemy(world, "shard", e.arena, { at: { x: e.pos.x + 12, y: e.pos.y } });
  }
}

function defuseBomb(world: World, b: Bomb) {
  world.bombs = world.bombs.filter((x) => x !== b);
  burst(world, b.pos, COLORS.green, 18);
  const pts = Math.floor(BOMB_POINTS * world.load.scoreMult);
  world.score += pts;
  floatText(world, b.pos, `DEFUSED +${pts}`, COLORS.green);
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
