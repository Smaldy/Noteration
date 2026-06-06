import { fileURLToPath, URL } from "node:url";

import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Frontend root is the repo root (`src/`). `npm run build` emits to `dist/`,
// which FastAPI serves. In dev, `/api` is proxied to the FastAPI server.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    // The single `vendor` chunk (React core + every eager runtime lib) can exceed
    // the default 500 kB notice; that's intentional here, so quiet the warning.
    chunkSizeWarningLimit: 1500,
    outDir: "dist",
    rollupOptions: {
      output: {
        // Only split libraries that are imported *exclusively* by lazy-loaded
        // routes (src/App.tsx). Those chunks are async — they always load and
        // initialize AFTER the eager `vendor` chunk — so splitting them is safe
        // and keeps the initial bundle small (the heavy stuff downloads with the
        // page that needs it: FullCalendar, TipTap, KaTeX, the markdown stack,
        // dnd-kit). DO NOT add an eagerly-imported (boot-path) library to this
        // list: a separate eager chunk that references React at module-init can
        // initialize before React does, blanking the whole app with
        // "Cannot set properties of undefined (setting 'Children')". Everything
        // eager (react, react-dom, react-router, framer-motion, i18next, zustand,
        // lucide, …) stays together in `vendor` so init order is never a hazard.
        manualChunks(id) {
          if (!id.includes("node_modules")) return undefined;
          if (id.includes("@fullcalendar")) return "fullcalendar";
          if (id.includes("katex")) return "katex";
          if (
            id.includes("@tiptap") ||
            id.includes("prosemirror") ||
            id.includes("tiptap-markdown")
          ) {
            return "editor";
          }
          if (
            /[\\/](react-markdown|remark|rehype|micromark|mdast|hast|unist|unified|vfile|property-information|decode-named-character-reference|character-entities|space-separated-tokens|comma-separated-tokens|trim-lines|zwitch|html-url-attributes)/.test(
              id,
            )
          ) {
            return "markdown";
          }
          if (id.includes("@dnd-kit")) return "dndkit";
          // Exercise Duplicator viz libs — imported ONLY by the lazy /duplicator
          // route (same async-only safety as the chunks above). Plotly is huge and
          // additionally dynamic-imported inside PlotlyRenderer, so it gets its own
          // chunk and stays out of vendor (which it would otherwise bloat ~4.5 MB).
          if (id.includes("plotly")) return "plotly";
          if (/[\\/](mafs|matter-js|mathjs)[\\/]/.test(id)) return "viz";
          return "vendor";
        },
      },
    },
  },
});
