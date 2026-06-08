/**
 * Scoped CRT-arcade styling for the minigame cabinet. Injected as a single
 * <style> tag inside the overlay (mirrors CreditsOverlay) so none of it leaks
 * into the real app's global CSS. All class names are arcade-prefixed.
 *
 * The chassis reads as a solid 3-D box (extruded marquee + a skewed right side
 * wall + a grounded shadow) while the CRT screen stays flat and readable. A
 * casino-style pull lever mounts on the right side.
 */

export const ARCADE_PIXEL = "arcade-pixel";

export const arcadeStyles = `
  .${ARCADE_PIXEL} {
    font-family: "Press Start 2P", ui-monospace, monospace;
    letter-spacing: 0.02em;
    line-height: 1.55;
  }

  /* Dark arcade hall behind the cabinet. */
  .arcade-room {
    background:
      radial-gradient(120% 80% at 50% -10%, rgba(80,30,120,0.5), transparent 55%),
      radial-gradient(80% 60% at 50% 120%, rgba(20,60,90,0.35), transparent 60%),
      rgba(3, 2, 8, 0.9);
    backdrop-filter: blur(3px);
  }

  /* ---- Cabinet chassis (faux-3-D box) ------------------------------------- */
  .arcade-cab { position: relative; }
  /* receding right side wall */
  .arcade-cab::before {
    content: ""; position: absolute; z-index: -2;
    top: 34px; bottom: 30px; right: -28px; width: 32px;
    background: linear-gradient(90deg, #281452 0%, #160a2e 60%, #0c0620 100%);
    transform: skewY(33deg); transform-origin: left top;
    border-radius: 0 12px 14px 0;
    box-shadow: inset -6px 0 18px rgba(0,0,0,0.6);
  }
  /* soft contact shadow on the floor */
  .arcade-cab::after {
    content: ""; position: absolute; z-index: -3;
    left: 6%; right: -2%; bottom: -30px; height: 46px;
    background: radial-gradient(55% 60% at 50% 0, rgba(0,0,0,0.65), transparent 72%);
    filter: blur(7px);
  }
  .arcade-cab-side {
    background: linear-gradient(100deg, #2c1656 0%, #1a0f3a 60%, #120a28 100%);
    border: 2px solid rgba(160,110,240,0.30);
    box-shadow:
      inset 2px 0 0 rgba(255,255,255,0.06),
      inset 0 0 60px rgba(120,70,220,0.16);
  }

  /* ---- Marquee: extruded 3-D block ---------------------------------------- */
  .arcade-marquee {
    position: relative;
    background:
      linear-gradient(180deg, rgba(255,255,255,0.12), transparent 38%),
      linear-gradient(180deg, #3d1f68, #25113f);
    border: 2px solid rgba(190,130,255,0.45);
    border-radius: 12px;
    box-shadow:
      0 9px 0 #190d30,                       /* bottom thickness → block, not banner */
      0 9px 0 2px #120824,
      0 18px 26px -8px rgba(0,0,0,0.6),
      0 0 40px -6px rgba(190,120,255,0.55),
      inset 0 0 24px rgba(255,170,255,0.16);
  }
  .arcade-marquee::before {  /* top highlight bevel for thickness */
    content: ""; position: absolute; left: 10px; right: 10px; top: 3px; height: 5px;
    border-radius: 999px;
    background: linear-gradient(90deg, transparent, rgba(255,210,255,0.55), transparent);
  }
  .arcade-marquee-title {
    background: linear-gradient(180deg, #fff 0%, #ffd6ff 45%, #ff7bd5 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
    filter: drop-shadow(0 0 12px rgba(255,120,220,0.7)) drop-shadow(0 2px 0 rgba(80,20,90,0.6));
  }

  /* ---- The CRT screen (wide, old-TV) -------------------------------------- */
  .arcade-tv {
    background: linear-gradient(160deg, #1c1330, #0c0820);
    border: 3px solid rgba(160,110,235,0.35);
    box-shadow: inset 0 2px 0 rgba(255,255,255,0.06), 0 10px 30px -10px rgba(0,0,0,0.8);
    padding: 16px; border-radius: 20px;
  }
  .arcade-screen {
    position: relative;
    aspect-ratio: 4 / 3;
    border-radius: 22px / 30px;
    background:
      radial-gradient(130% 120% at 50% 30%, rgba(20,70,90,0.4), rgba(1,6,12,0.98) 72%),
      #03060a;
    box-shadow:
      inset 0 0 90px rgba(0,0,0,0.95),
      inset 0 0 22px rgba(80,220,255,0.12),
      0 0 0 6px #05030c, 0 0 0 8px rgba(120,80,200,0.25);
    overflow: hidden;
  }
  .arcade-screen::before {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 5;
    background: repeating-linear-gradient(
      to bottom, rgba(255,255,255,0.05) 0, rgba(255,255,255,0.05) 1px, transparent 1px, transparent 3px);
  }
  .arcade-screen::after {
    content: ""; position: absolute; inset: 0; pointer-events: none; z-index: 6;
    background: radial-gradient(120% 120% at 50% 50%, transparent 52%, rgba(0,0,0,0.62) 100%);
    animation: arcade-flicker 6s infinite steps(60);
  }
  @keyframes arcade-flicker { 0%,96%,100%{opacity:1} 97%{opacity:0.85} 98%{opacity:0.97} }
  .arcade-screen-inner { position: absolute; inset: 0; z-index: 4; padding: 20px 24px; }

  /* ---- Control deck (angled) — directional buttons only ------------------- */
  .arcade-deck-wrap { perspective: 1100px; }
  .arcade-deck {
    transform: rotateX(18deg); transform-origin: top center;
    background: linear-gradient(180deg, #2a1854 0%, #1a0f3a 70%, #150b2c 100%);
    border: 2px solid rgba(160,110,240,0.22);
    border-radius: 18px;
    box-shadow:
      inset 0 3px 10px rgba(0,0,0,0.5),
      inset 0 14px 26px -16px rgba(255,255,255,0.10);
  }

  /* ---- Coin well (sits inside the continuous body, front-bottom) ---------- */
  .arcade-slot {
    background: linear-gradient(180deg, #2a1a4c, #160c2c);
    border: 2px solid rgba(170,120,245,0.35);
    border-radius: 12px;
    box-shadow: inset 0 3px 10px rgba(0,0,0,0.7), 0 2px 0 rgba(255,255,255,0.05);
  }
  .arcade-slot-mouth {
    width: 46px; height: 10px; border-radius: 4px;
    background: #05030a;
    box-shadow: inset 0 3px 5px rgba(0,0,0,0.95), 0 1px 0 rgba(255,255,255,0.10);
  }
  .arcade-coin {
    width: 24px; height: 24px; border-radius: 999px;
    background: radial-gradient(circle at 36% 30%, #fff1b0, #ffcf3a 45%, #d99412 100%);
    box-shadow: 0 0 12px rgba(255,200,60,0.75), inset 0 1px 2px rgba(255,255,255,0.8);
    display: grid; place-items: center; color: #8a5a00; font-weight: 900; font-size: 12px;
  }

  /* ---- Semi-3-D plastic buttons (single colour, glossy dome) -------------- */
  .arcade-btn {
    position: relative; display: grid; place-items: center;
    width: 54px; height: 54px; border-radius: 999px;
    color: rgba(255,255,255,0.92);
    background: radial-gradient(circle at 38% 26%, #ffb0b0 0%, #ff5b5b 34%, #ee2d2d 60%, #b81d1d 100%);
    border: 2px solid rgba(255,255,255,0.14);
    box-shadow:
      inset 0 4px 7px rgba(255,255,255,0.7),
      inset 0 -8px 12px rgba(120,0,0,0.55),
      0 9px 16px rgba(0,0,0,0.45),
      0 3px 0 rgba(80,0,0,0.35);
    transition: transform 0.07s ease, box-shadow 0.07s ease, filter 0.12s ease;
    cursor: pointer;
  }
  .arcade-btn:hover { filter: brightness(1.07); }
  .arcade-btn:active:not(:disabled), .arcade-btn-press {
    transform: translateY(5px) scale(0.97);
    box-shadow:
      inset 0 3px 6px rgba(255,255,255,0.55),
      inset 0 -5px 9px rgba(120,0,0,0.5),
      0 3px 7px rgba(0,0,0,0.4);
  }
  .arcade-btn:disabled { opacity: 0.4; cursor: not-allowed; }

  /* ---- Slot-machine pull lever (profile, mounts on the right wall) -------- */
  /* The hub is a chrome cylinder bolted to the cabinet side; a thick chrome
     shaft angles up to a big red ball. Drawn in profile (side-on). */
  .arcade-lever-hub {
    width: 38px; height: 38px; border-radius: 999px;
    background: radial-gradient(circle at 38% 30%, #f2f2f6 0%, #aeb0bd 38%, #5b5d6c 72%, #2c2d38 100%);
    box-shadow: 0 4px 10px rgba(0,0,0,0.6), inset 0 2px 3px rgba(255,255,255,0.7);
    border: 2px solid #3a3b47;
  }
  .arcade-lever-hub-bolt {
    width: 10px; height: 10px; border-radius: 999px;
    background: radial-gradient(circle at 40% 35%, #fff, #777 70%);
    box-shadow: inset 0 1px 1px rgba(0,0,0,0.4);
  }
  .arcade-lever-shaft {
    width: 16px; border-radius: 999px;
    /* brushed-chrome cylinder: bright centre highlight, dark edges */
    background: linear-gradient(90deg, #3f4250 0%, #9a9cab 26%, #fbfbff 50%, #9a9cab 74%, #3f4250 100%);
    box-shadow: 0 3px 8px rgba(0,0,0,0.5), inset 0 0 4px rgba(255,255,255,0.4);
  }
  .arcade-lever-knob {
    width: 54px; height: 54px; border-radius: 999px;
    background: radial-gradient(circle at 33% 26%, #ffc2c6 0%, #ff5566 30%, #e01e36 60%, #9e0f24 100%);
    box-shadow:
      0 8px 18px rgba(0,0,0,0.55),
      inset 0 6px 9px rgba(255,255,255,0.7),
      inset 0 -8px 12px rgba(110,0,18,0.55);
    border: 2px solid rgba(255,255,255,0.18);
  }

  /* ---- Neon text ----------------------------------------------------------- */
  .arcade-neon-cyan { color:#6ffbff; text-shadow:0 0 8px rgba(80,230,255,0.8),0 0 2px rgba(80,230,255,0.9); }
  .arcade-neon-pink { color:#ff7bd5; text-shadow:0 0 8px rgba(255,100,210,0.8),0 0 2px rgba(255,100,210,0.9); }
  .arcade-neon-yellow { color:#ffe14d; text-shadow:0 0 8px rgba(255,220,70,0.8),0 0 2px rgba(255,220,70,0.9); }
  .arcade-neon-green { color:#74ff9c; text-shadow:0 0 8px rgba(90,255,150,0.7),0 0 2px rgba(90,255,150,0.9); }
  .arcade-dim { color:#6274a0; }

  .arcade-blink { animation: arcade-blink 1.1s steps(2,start) infinite; }
  @keyframes arcade-blink { 0%,50%{opacity:1} 50.01%,100%{opacity:0} }

  .arcade-slam { animation: arcade-slam 0.6s cubic-bezier(0.2,1.6,0.36,1) both; }
  @keyframes arcade-slam {
    0% { transform: scale(6); opacity: 0; filter: blur(8px); }
    60% { opacity: 1; } 70% { transform: scale(0.92); }
    100% { transform: scale(1); opacity: 1; filter: blur(0); }
  }

  @media (prefers-reduced-motion: reduce) {
    .arcade-screen::after, .arcade-blink, .arcade-slam { animation: none; }
  }
`;
