/**
 * Scoped CRT-arcade styling for the minigame overlay. Injected as a single
 * <style> tag inside the overlay (mirrors CreditsOverlay) so none of it leaks
 * into the real app's global CSS. All class names are arcade-prefixed.
 */

export const ARCADE_PIXEL = "arcade-pixel";

export const arcadeStyles = `
  .${ARCADE_PIXEL} {
    font-family: "Press Start 2P", ui-monospace, monospace;
    letter-spacing: 0.04em;
    line-height: 1.5;
  }

  /* The cabinet bezel + dark room behind it. */
  .arcade-room {
    background:
      radial-gradient(120% 90% at 50% 0%, rgba(40,20,70,0.55), transparent 60%),
      rgba(4, 2, 10, 0.86);
    backdrop-filter: blur(2px);
  }
  .arcade-cabinet {
    background: linear-gradient(160deg, #1b1140 0%, #0d0820 60%, #060312 100%);
    border: 2px solid rgba(180, 120, 255, 0.35);
    box-shadow:
      0 0 0 4px rgba(0,0,0,0.6),
      0 0 60px -10px rgba(150, 90, 255, 0.5),
      inset 0 0 40px rgba(120, 70, 220, 0.18);
  }

  /* The glowing phosphor screen. */
  .arcade-screen {
    position: relative;
    background:
      radial-gradient(130% 120% at 50% 30%, rgba(20,60,80,0.35), rgba(2,8,14,0.96) 70%),
      #03060a;
    box-shadow:
      inset 0 0 70px rgba(0,0,0,0.9),
      inset 0 0 18px rgba(80,220,255,0.12);
    overflow: hidden;
  }
  .arcade-screen::before {
    /* Scanlines. */
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: repeating-linear-gradient(
      to bottom,
      rgba(255,255,255,0.05) 0px,
      rgba(255,255,255,0.05) 1px,
      transparent 1px,
      transparent 3px
    );
    z-index: 5;
  }
  .arcade-screen::after {
    /* Vignette + curvature haze + faint flicker. */
    content: "";
    position: absolute;
    inset: 0;
    pointer-events: none;
    background: radial-gradient(120% 120% at 50% 50%, transparent 55%, rgba(0,0,0,0.55) 100%);
    z-index: 6;
    animation: arcade-flicker 5s infinite steps(60);
  }
  @keyframes arcade-flicker {
    0%, 96%, 100% { opacity: 1; }
    97% { opacity: 0.86; }
    98% { opacity: 0.97; }
  }

  /* Neon text in classic arcade hues. */
  .arcade-neon-cyan { color: #6ffbff; text-shadow: 0 0 8px rgba(80,230,255,0.8), 0 0 2px rgba(80,230,255,0.9); }
  .arcade-neon-pink { color: #ff7bd5; text-shadow: 0 0 8px rgba(255,100,210,0.8), 0 0 2px rgba(255,100,210,0.9); }
  .arcade-neon-yellow { color: #ffe14d; text-shadow: 0 0 8px rgba(255,220,70,0.8), 0 0 2px rgba(255,220,70,0.9); }
  .arcade-neon-green { color: #74ff9c; text-shadow: 0 0 8px rgba(90,255,150,0.7), 0 0 2px rgba(90,255,150,0.9); }
  .arcade-dim { color: #5a6b8c; }

  .arcade-blink { animation: arcade-blink 1.1s steps(2, start) infinite; }
  @keyframes arcade-blink { 0%,50% { opacity: 1; } 50.01%,100% { opacity: 0; } }

  /* WAVE slam-in. */
  .arcade-slam {
    animation: arcade-slam 0.6s cubic-bezier(0.2, 1.6, 0.36, 1) both;
  }
  @keyframes arcade-slam {
    0% { transform: scale(6); opacity: 0; filter: blur(8px); }
    60% { opacity: 1; }
    70% { transform: scale(0.92); }
    100% { transform: scale(1); opacity: 1; filter: blur(0); }
  }

  /* Lever pull. */
  .arcade-lever-knob { transition: transform 0.45s cubic-bezier(0.34, 1.56, 0.64, 1); transform-origin: bottom center; }
  .arcade-lever-pulled .arcade-lever-knob { transform: translateY(34px) rotate(8deg); }

  @media (prefers-reduced-motion: reduce) {
    .arcade-screen::after, .arcade-blink, .arcade-slam { animation: none; }
  }
`;
