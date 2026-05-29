import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Frontend root is the repo root (`src/`). `npm run build` emits to `dist/`,
// which FastAPI serves. In dev, `/api` is proxied to the FastAPI server.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
  build: {
    outDir: "dist",
  },
});
