/**
 * ── THE CABINET, AS COORDINATES ─────────────────────────────────────────────
 * This is the ONLY file you edit to lay out the arcade machine. Every part is a
 * flat box at (x, y) with size (w, h) inside a fixed STAGE (origin = top-left,
 * x → right, y → down). Press **B** in the arcade overlay to flip to BLOCKOUT
 * mode: each part draws as a saturated-red shape with its label + live
 * `w×h · x,y` readout. Drag the numbers until the proportions feel right, then
 * the skin (fill/border/shadow already declared below) renders the same boxes.
 *
 * SHAPES        rect · round(r) · trap(taper) · oval        (see primitives.tsx)
 *               trap taper: +value → TOP narrower (faces up); −value → BOTTOM
 *               narrower (faces down). Magnitude = how strong the recede is.
 * CENTERING     a box is centered when its center = stage center. Horizontally:
 *               x = (STAGE_W − w) / 2 = 240 − w/2  →  center cx = 240.
 *               Vertically: y = (STAGE_H − h) / 2 = 380 − h/2  →  cy = 380.
 *               Blockout draws cyan dashed center lines and prints each box's
 *               c<cx>,<cy>; it shows ↔✓ when h-centered, ↕✓ when v-centered.
 * NAMING        kebab-case, region-first: marquee, hood, screen, deck,
 *               btn-left/right/up/down, lever, coin-slot, kick …
 * FUNCTIONAL    ids in FUNCTIONAL_SLOTS render the live element (CRT, buttons,
 *               lever, coin slot) in skin mode — but still show as a red box in
 *               blockout so you can place them.
 *
 * Array order = back-to-front draw order (z is the explicit override).
 */
import type { Part } from "./primitives";

export const STAGE_W = 480;
export const STAGE_H = 760;

/** Ids whose box is filled by a live interactive element, not a flat skin. */
export const FUNCTIONAL_SLOTS = new Set([
  "screen",
  "btn-left",
  "btn-right",
  "btn-up",
  "btn-down",
  "lever",
  "coin-slot",
]);

export const CABINET_PARTS: Part[] = [
  // ── Chassis ───────────────────────────────────────────────────────────────
  {
    id: "cabinet",
    shape: "rect",
    x: -93,
    y: 60,
    w: 666,
    h: 450,
    r: 20,
    z: 1,
    fill: "linear-gradient(180deg,#30205e 0%,#241640 52%,#150b2e 100%)",
    border: "1px solid rgba(150,110,225,0.30)",
    shadow:
      "0 45px 80px -12px rgba(0,0,0,0.75), inset 0 2px 0 rgba(200,165,255,0.14), inset 16px 0 34px rgba(0,0,0,0.38), inset -16px 0 34px rgba(0,0,0,0.38), inset 0 -46px 60px rgba(0,0,0,0.5)",
  },
  {
    id: "kick",
    shape: "rect",
    x: -241,
    y: 630,
    w: 962,
    h: 260,
    r: 10,
    z: 2,
    fill: "linear-gradient(180deg,#160c2e 0%,#0c0620 100%)",
    shadow:
      "inset 0 26px 40px rgba(0,0,0,0.62), inset 0 2px 0 rgba(150,110,220,0.07), inset 14px 0 30px rgba(0,0,0,0.4), inset -14px 0 30px rgba(0,0,0,0.4)",
  },

  // ── Marquee ────────────────────────────────────────────────────────────────
  {
    id: "marquee",
    shape: "rect",
    x: -160,
    y: -60,
    w: 800,
    h: 80,
    r: 10,
    z: 6,
    fill: "linear-gradient(180deg,#5f349c 0%,#3c1f6a 52%,#2a1450 100%)",
    border: "2px solid rgba(214,170,255,0.72)",
    shadow:
      "0 0 42px rgba(216,114,255,0.42), 0 12px 26px rgba(0,0,0,0.55), inset 0 3px 0 rgba(255,228,255,0.4), inset 0 -18px 28px rgba(18,4,38,0.72)",
  },

  // ── Hood (perspective panel under the marquee) ──────────────────────────────
  {
    id: "hood",
    shape: "trap",
    x: -160,
    y: 20,
    w: 800,
    h: 40,
    taper: -67, // negative → bottom narrower → faces DOWN
    z: 5,
    fill: "linear-gradient(180deg,#241646 0%,#140b2c 58%,#0b0522 100%)",
    shadow: "0 11px 16px rgba(0,0,0,0.58)",
  },

  // ── Screen ──────────────────────────────────────────────────────────────────
  {
    id: "bezel",
    shape: "round",
    x: -10,
    y: 90,
    w: 500,
    h: 380,
    r: 18,
    z: 4,
    fill: "radial-gradient(130% 120% at 50% 0%, #161031 0%, #08050f 72%)",
    border: "2px solid rgba(150,105,228,0.32)",
    shadow:
      "inset 0 3px 0 rgba(165,125,235,0.2), inset 0 0 44px rgba(0,0,0,0.92), inset 0 -14px 30px rgba(0,0,0,0.85), 0 16px 28px rgba(0,0,0,0.5)",
  },
  { id: "screen", shape: "round", x: 0, y: 100, w: 480, h: 360, r: 10, z: 5 },

  // ── Control deck (perspective panel) ────────────────────────────────────────
  {
    id: "deck",
    shape: "trap",
    x: -241,
    y: 510,
    w: 962,
    h: 120,
    taper: 148,
    z: 4,
    fill: "linear-gradient(180deg,#41297e 0%,#2c1c5e 42%,#1a1040 100%)",
    shadow: "0 20px 26px rgba(0,0,0,0.62)",
  },
  { id: "btn-left", shape: "oval", x: 160, y: 548, w: 50, h: 30, z: 7, label: "btn-left ◄" },
  { id: "btn-up", shape: "oval", x: 215, y: 525, w: 50, h: 30, z: 7, label: "btn-up ▲" },
  { id: "btn-down", shape: "oval", x: 215, y: 570, w: 50, h: 30, z: 7, label: "btn-down ▼" },
  { id: "btn-right", shape: "oval", x: 270, y: 548, w: 50, h: 30, z: 7, label: "btn-right ►" },

  // ── Lever (profile, mounted on the right side) ──────────────────────────────
  { id: "lever", shape: "rect", x: 575, y: 200, w: 30, h: 160, z: 8, label: "lever" },

  // ── Coin slot (front, low) ──────────────────────────────────────────────────
  { id: "coin-slot", shape: "round", x: 360, y: 680, w: 160, h: 80, r: 12, z: 6 },
];

/** Lookup helper so the stage can position functional slots by id. */
export function partById(id: string): Part | undefined {
  return CABINET_PARTS.find((p) => p.id === id);
}
