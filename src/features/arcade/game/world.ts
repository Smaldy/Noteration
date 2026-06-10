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
const ZAP_R = 64; // manual click hits enemies/bombs within this radius of the cursor
const ZAP_CD = 0.22;
const ZAP_DMG = 1;
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
  for (const a of ARENAS) arenas[a.id] = { pending: 0, queue: [], spawnTimer: 0 };

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
    slowmo: { active: 0, cooldown: 0 },
    arena: "library", // synced to the real route on mount
    enemies: [],
    spikes: [],
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
  }
  world.slowmo.active = Math.max(0, world.slowmo.active - dt);
  world.slowmo.cooldown = Math.max(0, world.slowmo.cooldown - dt);
  const edt = world.slowmo.active > 0 ? dt * SLOW_FACTOR : dt;

  stepPlayer(world, dt, input);
  stepWave(world, dt);
  stepEnemies(world, edt);
  stepSpikes(world, edt);
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

  // Click attack: a short-range zap (always) plus — once the Sidearm is owned —
  // a radiating burst of bullets. More Rapid Fire = more bullets per click.
  if (input.clicked && p.zapCd <= 0) {
    p.zapCd = ZAP_CD;
    world.zaps.push({ pos: { ...p.pos }, life: 0.26, maxLife: 0.26, radius: ZAP_R });
    const r2 = ZAP_R * ZAP_R;
    for (const e of world.enemies) {
      if (e.arena !== world.arena) continue;
      if (dist2(e.pos, p.pos) <= r2 + e.radius * e.radius) damageEnemy(world, e, ZAP_DMG);
    }
    if (world.load.canShoot) fireBurst(world);
  }

  // Hold the click on a bomb in this sector to defuse it: the meter fills over
  // `defuseTime`, and bleeds back down when you step off it.
  for (const b of world.bombs) {
    if (b.arena !== world.arena) continue;
    const reach = b.radius + DEFUSE_REACH;
    const onIt = dist2(b.pos, p.pos) <= reach * reach;
    if (input.held && onIt) {
      b.defuse += dt / b.defuseTime;
      if (b.defuse >= 1) defuseBomb(world, b);
    } else if (b.defuse > 0) {
      b.defuse = Math.max(0, b.defuse - dt * DEFUSE_DECAY);
    }
  }
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
    b.fuse -= dt;
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
  world.bombs.push({
    id: world.nextId++,
    arena,
    pos: { x: 80 + Math.random() * (world.w - 160), y: 110 + Math.random() * (world.h - 220) },
    fuse: BOMB_FUSE,
    maxFuse: BOMB_FUSE,
    defuse: 0,
    defuseTime: DEFUSE_MIN + Math.random() * (DEFUSE_MAX - DEFUSE_MIN),
    radius: BOMB_R,
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
