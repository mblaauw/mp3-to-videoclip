import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The shared renderer file imports remotion/react from its own package tree;
  // the Player must use the frontend's single copies or hooks see two runtimes.
  resolve: { dedupe: ["react", "react-dom", "remotion"] },
  server: {
    port: 5173,
    // The Player imports the renderer's own BaseFilm and timing module.
    fs: { allow: [".."] },
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
});