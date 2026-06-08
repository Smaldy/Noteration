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
    fill: "linear-gradient(180deg,#2a1656,#160a30)",
    border: "2px solid rgba(160,110,240,0.4)",
    shadow: "0 30px 60px rgba(0,0,0,0.6), inset 0 2px 0 rgba(255,255,255,0.06)",
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
    fill: "linear-gradient(180deg,#1c0e3a,#0b0518)",
    shadow: "inset 0 6px 14px rgba(0,0,0,0.6)",
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
    fill: "linear-gradient(180deg,#442375,#220e3b)",
    border: "3px solid rgba(195,140,255,0.55)",
    shadow: "0 0 26px rgba(255,140,240,0.25), inset 0 0 22px rgba(255,170,255,0.16)",
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
    fill: "linear-gradient(180deg,#1c1038,#0e0822)",
    shadow: "0 8px 12px rgba(0,0,0,0.5)",
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
    fill: "#070412",
    border: "2px solid rgba(140,90,220,0.25)",
    shadow: "inset 0 0 30px rgba(0,0,0,0.9)",
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
    fill: "linear-gradient(180deg,#2c1856,#160b2e)",
    shadow: "0 14px 18px rgba(0,0,0,0.6)",
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
