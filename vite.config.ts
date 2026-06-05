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
    outDir: "dist",
    rollupOptions: {
      output: {
        // Split heavy/independent libraries into their own chunks. Combined with
        // route-level code splitting (src/App.tsx), the on-demand libs
        // (FullCalendar, TipTap, KaTeX, the markdown stack) only download with
        // the page that imports them, keeping the initial bundle small.
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
          if (id.includes("framer-motion") || /[\\/]motion-dom[\\/]/.test(id)) {
            return "motion";
          }
          if (id.includes("@dnd-kit")) return "dndkit";
          if (id.includes("i18next")) return "i18n";
          if (
            /[\\/](react|react-dom|react-router|react-router-dom|scheduler)[\\/]/.test(id)
          ) {
            return "react-vendor";
          }
          return "vendor";
        },
      },
    },
  },
});
