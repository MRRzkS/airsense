import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  resolve: {
    // ESM config, so __dirname is not defined; resolve against the module URL.
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  build: {
    rollupOptions: {
      output: {
        // Recharts is over half the bundle and changes far less often than our
        // code; splitting it keeps the app chunk small across redeploys.
        manualChunks: { charts: ["recharts"] },
      },
    },
  },
  server: {
    host: true,
    port: 5173,
  },
});
