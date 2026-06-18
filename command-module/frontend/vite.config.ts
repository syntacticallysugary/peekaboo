import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [vue(), tailwindcss()],
  server: {
    proxy: {
      "/api":     "http://localhost:8081",
      "/health":  "http://localhost:8081",
      "/ws": { target: "ws://localhost:8081", ws: true },
    },
  },
  build: { outDir: "dist" },
});
