import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "./src") } },
  server: {
    port: 5173,
    host: "0.0.0.0",
    proxy: {
      // Keep /api/v1 intact for both fetch requests and event streams.
      "/api": { target: "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
