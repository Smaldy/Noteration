/**
 * NOTINVASION — canvas renderer. Pure draw: takes a `World` and paints one
 * frame onto a 2D context. No simulation happens here. Neon-on-dark to match the
 * cabinet's CRT; glow comes from `shadowBlur`.
 */
import { ARENAS, type Bomb, COLORS, type Enemy, type World } from "./types";

export function render(ctx: CanvasRenderingContext2D, world: World) {
  const { w, h } = world;
  ctx.save();

  // Screen shake.
  if (world.shake > 0.2) {
    const m = world.shake;
    ctx.translate((Math.random() - 0.5) * m, (Math.random() - 0.5) * m);
  }

  // Transparent arena — the frozen Noteration app shows through. The container
  // applies a faint dark wash for contrast; here we only lay a subtle grid so
  // the game elements read without hiding the app.
  ctx.clearRect(-40, -40, w + 80, h + 80);
  drawGrid(ctx, w, h);

  // Spikes (enemy projectiles).
  ctx.shadowBlur = 10;
  for (const s of world.spikes) {
    ctx.shadowColor = COLORS.pink;
    ctx.fillStyle = COLORS.pink;
    diamond(ctx, s.pos.x, s.pos.y, s.radius);
  }

  // Bullets (player).
  for (const b of world.bullets) {
    ctx.shadowColor = COLORS.cyan;
    ctx.fillStyle = COLORS.cyan;
    ctx.beginPath();
    ctx.arc(b.pos.x, b.pos.y, 4, 0, Math.PI * 2);
    ctx.fill();
  }

  // Bombs planted in this sector (the fuse ring shows time left to defuse).
  for (const b of world.bombs) if (b.arena === world.arena) drawBomb(ctx, b);

  // Enemies (only the active sector is live/visible).
  for (const e of world.enemies) if (e.arena === world.arena) drawEnemy(ctx, e);

  // Particles.
  ctx.shadowBlur = 6;
  for (const p of world.particles) {
    ctx.globalAlpha = Math.max(0, p.life / p.maxLife);
    ctx.shadowColor = p.color;
    ctx.fillStyle = p.color;
    ctx.fillRect(p.pos.x - p.size / 2, p.pos.y - p.size / 2, p.size, p.size);
  }
  ctx.globalAlpha = 1;

  // Click "zap" rings.
  ctx.shadowBlur = 12;
  for (const z of world.zaps) {
    const t = 1 - z.life / z.maxLife;
    ctx.globalAlpha = 1 - t;
    ctx.strokeStyle = COLORS.cyan;
    ctx.shadowColor = COLORS.cyan;
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(z.pos.x, z.pos.y, z.radius * (0.4 + t * 0.6), 0, Math.PI * 2);
    ctx.stroke();
  }
  ctx.globalAlpha = 1;

  // Floating score text.
  ctx.shadowBlur = 0;
  ctx.font = "16px 'Press Start 2P', monospace";
  ctx.textAlign = "center";
  for (const f of world.floats) {
    ctx.globalAlpha = Math.min(1, f.life * 2);
    ctx.fillStyle = f.color;
    ctx.fillText(f.text, f.pos.x, f.pos.y);
  }
  ctx.globalAlpha = 1;

  drawPlayer(ctx, world);
  ctx.restore();

  if (world.waveBanner > 0) drawBanner(ctx, world);
  if (world.bannerArena > 0) drawArenaBanner(ctx, world);
}

function drawBomb(ctx: CanvasRenderingContext2D, b: Bomb) {
  const t = b.fuse / b.maxFuse;
  const urgent = b.fuse < 3;
  const blink = urgent && Math.floor(b.fuse * 8) % 2 === 0;
  ctx.save();
  ctx.translate(b.pos.x, b.pos.y);
  ctx.shadowBlur = 16;
  // body
  const body = blink ? "#ffffff" : COLORS.pink;
  ctx.shadowColor = COLORS.pink;
  ctx.fillStyle = "rgba(255,123,213,0.15)";
  ctx.strokeStyle = body;
  ctx.lineWidth = 3;
  ctx.beginPath();
  ctx.arc(0, 0, b.radius, 0, Math.PI * 2);
  ctx.fill();
  ctx.stroke();
  // fuse arc (drains clockwise as the fuse burns)
  ctx.strokeStyle = urgent ? COLORS.pink : COLORS.yellow;
  ctx.shadowColor = ctx.strokeStyle;
  ctx.lineWidth = 4;
  ctx.beginPath();
  ctx.arc(0, 0, b.radius + 7, -Math.PI / 2, -Math.PI / 2 + t * Math.PI * 2);
  ctx.stroke();
  // defuse meter — fills green as you hold on the bomb
  if (b.defuse > 0) {
    ctx.strokeStyle = COLORS.green;
    ctx.shadowColor = COLORS.green;
    ctx.lineWidth = 5;
    ctx.beginPath();
    ctx.arc(0, 0, b.radius - 4, -Math.PI / 2, -Math.PI / 2 + b.defuse * Math.PI * 2);
    ctx.stroke();
  }
  // spark tick
  ctx.shadowBlur = 0;
  ctx.fillStyle = body;
  ctx.font = "bold 18px monospace";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("!", 0, 1);
  ctx.restore();
}

function drawGrid(ctx: CanvasRenderingContext2D, w: number, h: number) {
  ctx.shadowBlur = 0;
  ctx.strokeStyle = COLORS.grid;
  ctx.lineWidth = 1;
  const gap = 48;
  ctx.beginPath();
  for (let x = 0; x <= w; x += gap) {
    ctx.moveTo(x, 0);
    ctx.lineTo(x, h);
  }
  for (let y = 0; y <= h; y += gap) {
    ctx.moveTo(0, y);
    ctx.lineTo(w, y);
  }
  ctx.stroke();
}

function drawEnemy(ctx: CanvasRenderingContext2D, e: Enemy) {
  ctx.save();
  ctx.translate(e.pos.x, e.pos.y);
  ctx.rotate(e.spin);
  ctx.shadowBlur = 14;
  const flash = e.hitFlash > 0.5;

  if (e.kind === "clock") {
    const col = flash ? "#ffffff" : COLORS.pink;
    ctx.shadowColor = COLORS.pink;
    ctx.strokeStyle = col;
    ctx.fillStyle = "rgba(255,123,213,0.10)";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(0, 0, e.radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.stroke();
    // tick marks
    ctx.lineWidth = 2;
    for (let i = 0; i < 12; i++) {
      const a = (i / 12) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(Math.cos(a) * (e.radius - 5), Math.sin(a) * (e.radius - 5));
      ctx.lineTo(Math.cos(a) * (e.radius - 1), Math.sin(a) * (e.radius - 1));
      ctx.stroke();
    }
    // hands (counter-rotate so they spin against the body)
    ctx.rotate(-e.spin * 2.4);
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(0, 0);
    ctx.lineTo(0, -e.radius * 0.6);
    ctx.moveTo(0, 0);
    ctx.lineTo(e.radius * 0.45, e.radius * 0.2);
    ctx.stroke();
  } else {
    const small = e.kind === "shard";
    const col = flash ? "#ffffff" : small ? COLORS.green : COLORS.yellow;
    ctx.shadowColor = col;
    ctx.strokeStyle = col;
    ctx.fillStyle = small ? "rgba(116,255,156,0.12)" : "rgba(255,225,77,0.12)";
    ctx.lineWidth = small ? 2 : 3;
    const r = e.radius;
    // hourglass: two triangles tip-to-tip
    ctx.beginPath();
    ctx.moveTo(-r, -r);
    ctx.lineTo(r, -r);
    ctx.lineTo(0, 0);
    ctx.closePath();
    ctx.moveTo(-r, r);
    ctx.lineTo(r, r);
    ctx.lineTo(0, 0);
    ctx.closePath();
    ctx.fill();
    ctx.stroke();
  }
  ctx.restore();
}

function drawPlayer(ctx: CanvasRenderingContext2D, world: World) {
  const p = world.player;
  const { x, y } = p.pos;
  // Flicker while invulnerable.
  if (p.invuln > 0 && Math.floor(p.invuln * 12) % 2 === 0) return;
  ctx.save();
  ctx.translate(x, y);
  ctx.shadowBlur = 14;
  const col = p.hurt > 0 ? COLORS.pink : world.slowmo.active > 0 ? COLORS.yellow : COLORS.cyan;
  ctx.shadowColor = col;
  ctx.strokeStyle = col;
  ctx.lineWidth = 2;
  // reticle ring + crosshair
  ctx.beginPath();
  ctx.arc(0, 0, 11, 0, Math.PI * 2);
  ctx.stroke();
  ctx.beginPath();
  ctx.moveTo(-16, 0);
  ctx.lineTo(-6, 0);
  ctx.moveTo(6, 0);
  ctx.lineTo(16, 0);
  ctx.moveTo(0, -16);
  ctx.lineTo(0, -6);
  ctx.moveTo(0, 6);
  ctx.lineTo(0, 16);
  ctx.stroke();
  ctx.fillStyle = col;
  ctx.beginPath();
  ctx.arc(0, 0, 2.5, 0, Math.PI * 2);
  ctx.fill();
  ctx.restore();
}

function drawBanner(ctx: CanvasRenderingContext2D, world: World) {
  const a = Math.min(1, world.waveBanner * 1.5);
  ctx.save();
  ctx.globalAlpha = a;
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.shadowBlur = 16;
  ctx.shadowColor = COLORS.cyan;
  ctx.fillStyle = COLORS.cyan;
  ctx.font = "14px 'Press Start 2P', monospace";
  ctx.fillText("WAVE", world.w / 2, world.h / 2 - 26);
  ctx.shadowColor = COLORS.pink;
  ctx.fillStyle = COLORS.pink;
  ctx.font = "48px 'Press Start 2P', monospace";
  ctx.fillText(String(world.arenas[world.arena].wave), world.w / 2, world.h / 2 + 24);
  ctx.restore();
}

function drawArenaBanner(ctx: CanvasRenderingContext2D, world: World) {
  const def = ARENAS.find((x) => x.id === world.arena);
  if (!def) return;
  ctx.save();
  ctx.globalAlpha = Math.min(1, world.bannerArena * 2);
  ctx.textAlign = "center";
  ctx.textBaseline = "alphabetic";
  ctx.shadowBlur = 14;
  ctx.shadowColor = def.color;
  ctx.fillStyle = def.color;
  ctx.font = "12px 'Press Start 2P', monospace";
  ctx.fillText(`▶ ${def.label} SECTOR`, world.w / 2, 92);
  ctx.restore();
}

function diamond(ctx: CanvasRenderingContext2D, x: number, y: number, r: number) {
  ctx.beginPath();
  ctx.moveTo(x, y - r);
  ctx.lineTo(x + r, y);
  ctx.lineTo(x, y + r);
  ctx.lineTo(x - r, y);
  ctx.closePath();
  ctx.fill();
}
