import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// base: "./" so the built assets load when Flask serves them from any path.
export default defineConfig({
  plugins: [react()],
  base: "./",
  server: {
    port: 5173,
    proxy: {
      // During `npm run dev`, forward API calls to the Flask backend.
      "/api": "http://localhost:7860",
    },
  },
  build: {
    outDir: "dist",
  },
});
